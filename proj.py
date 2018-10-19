from bs4 import BeautifulSoup
from bson import json_util
from flask import Flask, request, jsonify, abort, session, escape
from os import listdir, makedirs, urandom
from os.path import dirname, exists, isfile, realpath
from pymongo import MongoClient
from requests import get
from json import dumps, loads
import re

app = Flask(__name__)
app.secret_key = urandom(24)
resdir = dirname(realpath(__file__)) + "/resources/"
ing_rcps = {}

@app.route("/", methods = ["GET"])
def greet():
    if 'email' in session:
        return 'Logged in as %s' % escape(session['email'])
    return 'Hi, you are not logged in'

# Signs user in and redirects to homepage
@app.route('/login', methods = ["POST"])
def login():
    if request.method == "POST":
        email = request.get_json()['email']
        password = request.get_json()['password']
        db = connect_db()
        res = db.users.find_one({"email": email})
        if res and password == res['password']:
            session['email'] = email
            return dumps({'success': True}), 200, {'ContentType': 'application/json'}
    return dumps({'success': False, 'error': 'Wrong credentials'}), 200, {'ContentType': 'application/json'}

# Logs user out and redirects to homepage
@app.route('/logout')
def logout():
    # remove the email from the session if it's there
    session.pop('email', None)
    return dumps({'success': True}), 200, {'ContentType': 'application/json'}

# Connects to mLab's MongoDB and returns connection
def connect_db():
    DB_NAME = "comp9323"
    DB_HOST = "ds251112.mlab.com"
    DB_PORT = 51112
    DB_USER = "admin" # "admin@admin.com"
    DB_PASS = "admin18"

    connection = MongoClient(DB_HOST, DB_PORT)
    db = connection[DB_NAME]
    db.authenticate(DB_USER, DB_PASS)

    return db

# Returns requested columns from a collection
# Takes in JSON request where key1=collection, key2=columns
# https://docs.mongodb.com/manual/tutorial/project-fields-from-query-results/
@app.route("/collection-fields", methods = ["GET", "POST"])
def get_collection_fields():
    db = connect_db()
    # content = request.json
    # content = jsonify({
    #     'collection':'users',
    #     'fields': ["email", "password"]
    # })
    if request.json is None:
        abort(400, 'No valid JSON not provided')
    else:
        col = request.get_json()['collection']
        fields = request.get_json()['fields']

    query = {}
    query['_id'] = 0
    for f in fields:
        query[f] = 1
    cursor = db[col].find({}, query)
    json_docs = []
    for doc in cursor:
        json_docs.append(doc)
    return jsonify(json_docs)

# Returns recipes that contains searched ingredients
# Takes in JSON request where key1=array of ingredients
@app.route("/cuisines", methods=['Get'])
def search_db_cuisines():
    db=connect_db()
    abort(400, 'API not fully implemented yet')

# Returns recipes that contains searched ingredients
# Takes in JSON request where key1=array of ingredients
# Inserts all scraped recipes into database
def insert_db_recipes():
    db = connect_db()
    db.recipes.drop()
    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname, encoding = 'utf-8') as f:
            for line in f.readlines():
                recipe_obj = loads(line)
                recipe_obj["recipe_id"] = (recipe_obj.pop("_id"))["$oid"]
                recipe_obj["ts"]["date"] = recipe_obj["ts"].pop("$date")
                db.recipes.insert(recipe_obj)

def get_ingredient_refence():
    from textblob.inflect import singularize

    def oxford_reference_ing():
        oxfordreference_base_url = "http://www.oxfordreference.com/view/10.1093/acref/9780199234875.001.0001/acref-9780199234875"
        tag_filter = {"class" : "contentItem oxencycl-entry locked hasCover chunkResult hi-visible p-4 border-top"}
        i, ing_list = 1, []
        while True:
            url = oxfordreference_base_url + "?page=" + str(i) + "&pageSize=100"

            print(url)

            soup = BeautifulSoup(get(url).text, "lxml")
            l = soup.find_all("div", tag_filter)
            if not l:
                break
            for ing_div in l:
                content_list = ing_div.h2.a.contents
                if len(content_list) == 1:
                    content_split = content_list[0].split(",")
                    ings = []
                    if len(content_split) > 2:
                        for content in content_split:
                            ings.append(content.strip())
                    elif len(content_split) == 2:
                        ings.append(content_split[1].strip() + " " + content_split[0].strip())
                    else:
                        ings.append(content_split[0].strip())
                    for ing in ings:
                        if len(ing) > 2 and not ing.startswith("free ") and not ing.startswith("food ") and\
                        not re.match("^.*[A-Z].*$", ing) and not re.match("^.*[\u2010-\u2015\-]$", ing):
                            ing = re.sub("\(.*\)", "", ing).strip()
                            if not ing:
                                continue
                            ing_split = ing.split(" ")
                            ing_list.append((' '.join(ing_split[: -1]) + " " + singularize(ing_split[-1])).strip())
            i += 1

        return ing_list

    def wiki_cookbook_ing():
        from bs4 import Comment

        def ul_children(sib):
            l = []
            if not sib.name == "ul":
                if sib.name:
                    l.append(sib.a.contents[0])
            else:
                for child in sib.findAll(["li", "ul"]):
                    l += ul_children(child)

            return l

        wikicookbook_url = "https://en.wikibooks.org/wiki/Cookbook:Ingredients"
        soup = BeautifulSoup(get(wikicookbook_url).text, "lxml")
        l, ing_list = soup.find_all("h2"), set()
        for title_tag in l:
            if not title_tag.span:
                continue
            for sibling in title_tag.next_siblings:
                if sibling.name == "h2" or isinstance(sibling, Comment):
                    break
                l_alphabet_ing = ul_children(sibling)
                if l_alphabet_ing:
                    for ing in l_alphabet_ing:
                        ing = re.sub("\(.*\)", "", ing).strip()
                        if ing.startswith("Dairy products and ") or ing.endswith(" family"):
                            continue
                        ing_words = ing.split(",")
                        if len(ing_words) > 1:
                            ing = ing_words[1].strip() + " " + ing_words[0].strip()
                        else:
                            ing = ing_words[0].strip()
                        ing_words = ing.split(" ")
                        ing_list.add((" ".join(ing_words[: -1]) + " " + singularize(ing_words[-1])).lower().strip())

        return list(ing_list)

    fname = "ing_list"
    if isfile(resdir + fname):
        return
    l_ing = list(set(oxford_reference_ing() + wiki_cookbook_ing()))
    with open(resdir + fname, "w") as f:
        for t in sorted(l_ing):
            f.writelines(t + "\n")

# Scrape several websites for recipes
def get_recipes():
    from datetime import datetime
    from time import time

    def get_openrecipes():
        from os import chdir, remove
        from shutil import copyfileobj
        from wget import download
        import gzip

        fname = "20170107-061401-recipeitems.json"
        if not isfile(resdir + fname):
            chdir(resdir)
            download("https://s3.amazonaws.com/openrecipes/" + fname + ".gz")
            with gzip.open(fname + ".gz", 'rb') as f_in:
                with open(fname, 'wb') as f_out:
                    copyfileobj(f_in, f_out)
            remove(resdir + fname + ".gz")

            return True

        return False

    def get_chowdown():
        fname = "chowdown-recipes.json"

        if isfile(resdir + fname):
            return False

        chowdown_base_url = "http://chowdown.io"
        soup = BeautifulSoup(get(chowdown_base_url).text, "lxml")
        tag_filter = {"class" : "sm-col sm-col-6 md-col-6 lg-col-4 xs-px1 xs-mb2"}
        for i, tag in enumerate(soup.find_all("div", tag_filter)):
            url = chowdown_base_url + tag.a.attrs["href"]
            soup1 = BeautifulSoup(get(url).text, "lxml")
            d = {"_id" : {"$oid" : "chowdown" + str(i)},
                 "name" : soup1.title.contents[0],
                 "url" : url,
                 "ts" : {"$date" : round(time())},
                 "cookTime" : "P",
                 "source" : "chowdown",
                 "recipeYield" : -1,
                 "datePublished" : str(datetime.now().strftime("%Y-%m-%d")),
                 "prepTime" : "P",
                 "image" : chowdown_base_url + soup1.find_all("img")[0].attrs["src"]}
            tag_filter = {"class" : "sm-col-8 center mx-auto"}
            remove_hyperlink = BeautifulSoup(str(soup1.find("div", tag_filter).p), "lxml")
            for a in remove_hyperlink.findAll('a'):
                a.replaceWithChildren()
            d["description"] = "".join(remove_hyperlink.p.contents)
            tag_filter = {"itemprop" : "recipeIngredient"}
            d["ingredients"] = "\n".join([ing.p.contents[0]
                                          for ing in soup1.find_all("li", tag_filter)])
            with open(resdir + fname, "a") as f:
                f.write(str(d).replace("'", "\"") + "\n")

        return True

    if get_openrecipes() or get_chowdown():
        return
        insert_db_recipes()

def scrape_ingredients():
    # from nltk.corpus import wordnet
    from textblob.inflect import singularize

    def symspell_correction(misspelled):
        from symspellpy import SymSpell, Verbosity

        sym_spell = SymSpell(83000, 2)
        dictionary_path = resdir + "frequency_dictionary_en_82_765.txt"
        if not sym_spell.load_dictionary(dictionary_path, 0, 1):
            return ""
        suggestions = sym_spell.lookup(misspelled, Verbosity.CLOSEST, 2)
        if suggestions:
            return sorted(suggestions, key = lambda x: x.count, reverse = True)[0].term
        return sorted(sym_spell.lookup_compound(misspelled, 2),\
                      key = lambda x: x.count,\
                      reverse = True)[0].term

    units_regex, units_set, ings = "", set(), set()
    with open(resdir + "units", "r") as f:
        tmp = [line.strip() for line in f]
        units_regex = re.sub("(\.|\#)", r"\\\1", "|".join(tmp))
        units_set = set(tmp)
    quantity_filter = "[\u2150-\u215e\u00bc-\u00be\u0030-\u0039]\s*("\
                          + units_regex + ")*(\s*\)\s*of\s+|\s+of\s+|\s*\)\s*|\s+)"\
                          + "([\u24C7\u2122\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u01bf\u01cd-\u02af\u0061-\u007a\ \-]{2,})"
    d_ing = {}
    with open(resdir + "ing_list", "r", encoding = 'utf-8') as f:
        ings = set([line.strip() for line in f])
    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname, encoding = 'utf-8') as f:
            for k, line in enumerate(f.readlines()):
                # print(k)
                ing_line, recipe_id = loads(line), ""
                if "$oid" in ing_line["_id"]:
                    recipe_id = ing_line["_id"]["$oid"]
                else:
                    recipe_id = ing_line["_id"]["oid"]
                for ing_str in re.split("\n|,", ing_line["ingredients"].lower().strip()):
                    ing_str = re.findall(quantity_filter, ing_str)
                    if not ing_str or len(ing_str) > 1:
                        continue
                    # maybe split on stopwords
                    for ing_str_split in re.split("\s+(and|or|with|in)\s+", ing_str[0][-1].strip()):
                        ing, ing_str_tokens = "", list(reversed(ing_str_split.split(" ")))
                        for i, token in enumerate(ing_str_tokens):
                            token = token.strip()
                            if not token or re.match("^[a-z]+([\u002d\u2010-\u2015][a-z]+)+$", token):
                                continue
                            # if token not in ings and not wordnet.synsets(token):
                            #     token = symspell_correction(token)
                            if not ing:
                                token = singularize(token)
                            if token not in ings or token in units_set:
                                continue
                            ing = token
                            for j in range(i + 1, len(ing_str_tokens)):
                                tmp = " ".join(reversed(ing_str_tokens[i + 1 : j + 1]))
                                if tmp + " " + ing not in ings:
                                    ing = " ".join(reversed(ing_str_tokens[i + 1 : j])) + " " + ing
                                    break
                            break
                        ing = ing.strip()
                        if len(ing) > 2:
                            ing = ing.strip()
                            if ing not in d_ing.keys():
                                d_ing[ing] = set()
                            d_ing[ing].add(recipe_id)

    return d_ing

# Returns all ingredients scraped from recipes
@app.route("/ingredients", methods = ["GET"])
def get_ingredients():
    return dumps({"ingredients" : sorted(list(ing_rcps.keys()))}), 200

# GET /recipes -  Returns all recipes' data e.g. name, ingredients, image, etc
# Usage eg: http://127.0.0.1:5000/recipes
# GET /recipes-search - Returns single recipe's data e.g. name, ingredients, image, etc
# Usage eg: http://127.0.0.1:5000/recipes-search?ingredients=onion,carrot
#           http://127.0.0.1:5000/recipes/5160756d96cc62079cc2db16,chowdown0
@app.route("/recipes", methods=['GET'])
@app.route("/recipes/<recipe_ids>", methods = ["GET"])
@app.route("/recipes-search", methods = ["GET"])
def get_db_recipe(recipe_ids = "", size = 80):
    db = connect_db()
    if request.url_rule.rule == '/recipes':
        res=db.tasteRecipes.find()
        recipe_array = []
        for doc in res:
            recipe_array.append(doc)
        array_sanitized = loads(json_util.dumps(recipe_array))
        return jsonify(array_sanitized)
    if request.url_rule.rule == '/recipes-search':
        if "ingredients" not in request.args:
            return dumps({"result" : "missing ingredients parameter"}), 400
        l_ing = request.args.get("ingredients")
    if "size" in request.args:
        try:
            size = int(request.args.get("size"))
        except ValueError:
            pass

    if recipe_ids:
        # from bson.objectid import ObjectId

        # res = db.recipes.find_one({"_id": ObjectId(recipe_ids)})
        # json_res = []
        # for doc in res:
        #     # print(doc)
        #     json_row = dumps(res[doc], default = json_util.default)
        #     # json_row = {doc:res[doc]}
        #     json_res.append(json_row)
        #
        # return jsonify(json_res), 200

        recipe_ids = sorted(recipe_ids.strip().lower().split(","))
        lines, recipes = [], []
        for fname in listdir(resdir):
            if not isfile(resdir + fname) or not fname.endswith(".json"):
                continue
            with open(resdir + fname, encoding = 'utf-8') as f:
                lines = lines + f.readlines()
        for i, line in enumerate(lines):
            # print(i)
            line = loads(line)
            if line["_id"]["$oid"] in recipe_ids:
                recipes.append(line)
                if len(recipes) == size:
                    break

        return dumps({"result" : recipes, "size" : len(recipes)}), 200
    else:
        tmp = set()
        for i, ing in enumerate(l_ing.strip().lower().split(',')):
            ing = ing.strip()
            if i == 0:
                tmp = ing_rcps[ing]
            else:
                tmp = tmp.intersection(ing_rcps[ing])
        recipes = loads(get_db_recipe(",".join(tmp), size)[0])["result"]

        return dumps({"result" : recipes, "size" : len(recipes)}), 200

# POST    - creates new user
# PUT     - updates user details.
# DELETE  - deletes user
@app.route("/users", methods = ["POST", "PUT", "DELETE"])
def handle_users():
    sc = 1
    db = connect_db()
    if request.method == 'POST':
        email = request.get_json()['email']
        password = request.get_json()['password']
        fName = request.get_json()['first_name']
        lName = request.get_json()['last_name']
        sc = db.users.insert({"email": email, "password": password, "first_name": fName, "last_name": lName})
    else:
        #Following methods require user to be logged in
        if not 'email' in session:
            return dumps({'success': False, 'error': "You need to be logged in first."}), 401,\
                         {'ContentType': 'application/json'}
        currEmail = session['email']

        if request.method == "DELETE":
            sc = db.users.delete_one({"email": currEmail})
        elif request.json is None:
            abort(400, 'No valid JSON not provided')
        elif request.method == "PUT":
            print(3)
            email = request.get_json()['email']
            password = request.get_json()['password']
            fName = request.get_json()['fname']
            lName = request.get_json()['lname']

            query = {}
            if email:
                query["email"] = email
            if password:
                query["password"] = password
            if fName:
                query["first_name"] = fName
            if lName:
                query["last_name"] = lName

            '''
            query is in format of:
             {
                'email':email,
                'password': password,
                'first_name': fName,
                'last_name': lName
            }
            '''
            sc = db.users.update(
                {'email': currEmail},
                query
            )
    if sc:
        return dumps({'success': True}), 200, {'ContentType': 'application/json'}
    else:
        return dumps({'success': False}), 401, {'ContentType': 'application/json'}

# GET     - returns all favourited recipes for this user
# POST    - creates new favourite for a logged in user
# DELETE  - deletes favourite
@app.route("/favourites", methods = ["GET", "POST"])
def handle_favourites():
    # check if user is logged in first
    if not 'email' in session:
        return dumps({'success': False, 'error': "You need to be logged in first."}), 401, {
            'ContentType': 'application/json'}
    currEmail = session['email']
    db = connect_db()
    if request.method == 'GET':
        cursor = db.favourites.find({"email": currEmail})
        json_docs = []

        for doc in cursor:
            print(doc["recipe_id"])
            json_docs.append(doc["recipe_id"])
        return jsonify(json_docs) #TODO return recipe details, not just recipe IDs
    elif request.json is None:
        abort(400, 'No valid JSON not provided')
    elif request.method == 'POST':
        recipe_id = request.get_json()['recipe_id']
        sc = db.favourites.insert({"email": currEmail, "recipe_id": recipe_id})

    if sc:
        return dumps({'success': True}), 200, {'ContentType': 'application/json'}
    else:
        return dumps({'success': False}), 401, {'ContentType': 'application/json'}

# DELETE  - deletes specified favourite
@app.route("/favourites/<recipe_id>", methods = ["DELETE"])
def handle_favourite(recipe_id):
    # check if user is logged in first
    if not 'email' in session:
        return dumps({'success': False, 'error': "You need to be logged in first."}), 401,\
                     {'ContentType': 'application/json'}
    currEmail = session['email']
    db = connect_db()
    sc = 1
    if request.method == "DELETE":
        sc = db.favourites.delete_many({"email": currEmail, "recipe_id":recipe_id})

    if sc:
        return dumps({'success': True}), 200, {'ContentType': 'application/json'}
    else:
        return dumps({'success': False}), 401, {'ContentType': 'application/json'}

if __name__ == '__main__':
    if not exists(resdir):
        makedirs(resdir)
    get_ingredient_refence()
    get_recipes()
    ing_rcps = scrape_ingredients()
    app.run()
    # app.run(port = "5001")

#1313