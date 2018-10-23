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
ing_rcps = {} # ingredients and their list of respecitvely associated recipes
rcp_ings = {} # recipes and how many ingredients each recipe has

@app.route("/", methods = ["GET"])
def greet():
    if "email" in session:
        return 'Logged in as %s' % escape(session["email"])
    return 'Hi, you are not logged in'

# Signs user in and redirects to homepage.
# Also allows toggling between keeping user signed in or not
@app.route("/login", methods = ["POST"])
def login():
    if request.method == "POST":
        try:
            email = request.get_json()["email"]
            password = request.get_json()["password"]
            keepSignedIn = request.get_json()["keep_signed_in"]
        except:
            return dumps({"error": "Need: email, password, keep_signed_in"}), 401, {
                "ContentType": "application/json"}
        if keepSignedIn:
            session.permanent = True
        else:
            session.permanent = False
        db = connect_db()
        res = db.users.find_one({"email": email})
        if res and password == res["password"]:
            session["email"] = email

            return dumps({"success": True}), 200, {"ContentType": "application/json"}

    return dumps({"error": 'Wrong credentials'}), 400, {"ContentType": "application/json"}

# Logs user out and redirects to homepage
@app.route("/logout")
def logout():
    # remove the email from the session if it's there
    session.pop("email", None)
    return dumps({"success": True}), 200, {"ContentType": "application/json"}

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
# Inserts all scraped recipes into database
def insert_db_recipes():
    from bson import json_util

    db = connect_db()
    db.recipes.drop()
    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname, encoding = 'utf-8') as f:
            for line in f.readlines():
                try:
                    db.recipes.insert(json_util.loads(line))
                except:
                    pass

# Getting a list of all possible ingredients to help identifying ingredients during scraping process
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

    def get_openrecipes(): # made redundant since recipes don't have methods
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
            d = {"name" : soup1.title.contents[0],
                 "url" : url,
                 "ts" : {"date" : round(time())},
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

    def get_taste():
        def get_taste_recipe_info(a_collection_page, collection_link_path, fname, id_count, first_run_flag):
            recipe_section = a_collection_page.find(["main"])
            # repeat go into each recipe for X pages in collectoin e.g. in Indian food collection get each recipe
            for i, recipe in enumerate(recipe_section.find_all(['li'], class_ = "col-xs-6")):
                recipe_link_path = recipe.figure.a["href"]
                recipe_link = BeautifulSoup(get("https://www.taste.com.au" + recipe_link_path).text, "html.parser")
                d = {"||url||": "||" + "https://www.taste.com.au" + recipe_link_path + "||"}
                print(recipe_link_path)

                # open each recipe and get details
                d["||source||"] = "||" + "taste" + "||"
                d["||ts||"] = {"||date||": round(time())}
                d["||datePublished||"] = "||" + str(datetime.now().strftime("%Y-%m-%d")) + "||"
                d["||collectionName||"] = "||" + collection_link_path + "||"
                # name
                name = recipe_link.find(["div"], class_ = "col-xs-12").h1.text
                id_count = id_count + 1
                d["||name||"] = "||" + name + "||".replace("'", "").replace("\"", "")

                for recipe in recipe_link.find_all(["main"], class_ = "col-xs-12"):
                    # ingredient
                    for ingredient in recipe.find_all("div", class_ = "ingredient-description"):
                        ing = ingredient.text
                        d.setdefault("||ingredients||", []).append("||" + ing + "||".replace("\"", ""))

                    # method
                    for m in recipe.find_all("div", class_ = "recipe-method-step-content"):
                        method = m.text
                        method = re.sub('\n', '', method)
                        method = re.sub(' +', ' ', method).lstrip().rstrip()
                        d.setdefault("||method||", []).append("||" + method + "||".replace("\"", ""))

                    # recipe info (cooktime, preptime, servings)
                    for recipe_info_section in recipe.find_all("div", class_ = "cooking-info-lead-image-container col-xs-12 col-sm-8"):
                        for info in recipe_info_section.find_all('li'):
                            info = info.text
                            if "Cook" in info:
                                cook = re.sub("[a-zA-Z]", "", info).strip()
                                d["||cookTime||"] = "||" + cook + "||"
                            elif "Prep" in info:
                                d["||prepTime||"] = "||" + re.sub("[a-zA-Z]", "", info).strip() + "||"
                            elif "Makes" in info:
                                d["||recipeYield||"] = "||" + info.strip() + "||"
                            elif "Servings" in info:
                                d["||recipeYield||"] = "||" + info.strip() + "||"

                    # image
                    image = recipe.img["src"]
                    d["||image||"] = "||" + image + "||"

                    d["||description||"] = "||" + recipe.find("div", class_ = "single-asset-description-block").p.text.replace("\"", "") + "||"

                    # CREATING FILE
                    with open(resdir + fname, "a") as f:
                        f.write(str(d).replace("'||", "\"").replace("||'", "\"").replace("||", "").replace('\\xa0', '')+ "\n")

            return id_count

        id_count, first_run_flag = -1, False
        fname = "taste-recipes.json"

        if isfile(resdir + fname):
            return False

        for collection_page in range(1, 51):
            soup = BeautifulSoup(get("https://www.taste.com.au/recipes/collections?page=" + str(collection_page)\
                                                                                          + "&sort=recent").text, "html.parser")
            # for each page containing recipe folders
            for url in soup.find_all('article'):
                collection_link_path = url.figure.a["href"]

                # opens each recipe collection eg https://www.taste.com.au/recipes/collections/indian-curry-recipes
                a_collection_page = BeautifulSoup(get("https://www.taste.com.au" + collection_link_path).text, "html.parser")
                # traverse each page in collection
                if a_collection_page.find("div", class_ = "col-xs-8 pages"):
                    num_section = a_collection_page.find("div", class_ = "col-xs-8 pages")
                    for link in num_section.find_all('a'):
                        num_pages = link.text
                    # For every page in A collection eg pages 1-8 in Indian Recipe Collection
                    for i in range(1, int(num_pages) + 1):
                        print("NEXT page: " + "https://www.taste.com.au" + collection_link_path+ "?page=" + str(i) + "&q=&sort=recent")
                        a_collection_page = BeautifulSoup(get("https://www.taste.com.au" + collection_link_path\
                                                                                         + "?page=" + str(i)\
                                                                                         + "&q=&sort=recent").text, "html.parser")
                        id_count = get_taste_recipe_info(a_collection_page, collection_link_path, fname, id_count, first_run_flag)

                else: # there is only 1 page in collection
                    a_collection_page = BeautifulSoup(get("https://www.taste.com.au" + collection_link_path).text, "html.parser")
                    id_count = get_taste_recipe_info(a_collection_page, collection_link_path, fname, id_count, first_run_flag)

        return True

    if not (get_openrecipes() and get_chowdown() and get_taste()):
        insert_db_recipes()

# Ingredient scraper that looks at recipes and extract useful insight on top of indexing them for better performance
def scrape_ingredients():
    # from nltk.corpus import wordnet
    from textblob.inflect import singularize

    def symspell_correction(misspelled): # not used because it is too expensive
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
    d_ing, d_rcp = {}, {}
    with open(resdir + "ing_list", "r", encoding = 'utf-8') as f:
        ings = set([line.strip() for line in f])

    db = connect_db()
    cursor = db.recipes.find({})
    for k, doc in enumerate(cursor):
        print(k)
        recipe_id = str(doc["_id"])
        d_rcp[recipe_id] = 0
        for ing_str in doc["ingredients"]:
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
                    d_rcp[recipe_id] = d_rcp[recipe_id] + 1

    d_ing = {key : list(value) for key, value in d_ing.items()}
    with open(resdir + "ing_rcps", "w") as f1, open(resdir + "rcp_ings", "w") as f2:
        f1.write(dumps(d_ing))
        f2.write(dumps(d_rcp))

    return d_ing, d_rcp

# Returns all ingredients scraped from recipes
@app.route("/ingredients", methods = ["GET"])
def get_ingredients():
    tmp = list(ing_rcps.keys())

    return dumps({"ingredients" : sorted(tmp), "size" : len(tmp)}), 200

# GET /recipes - Returns all queried recipes' data e.g. name, ingredients, image, etc
# Usage eg: http://127.0.0.1:5000/recipes
#           http://127.0.0.1:5000/recipes?ingredients=onion,carrot
#           http://127.0.0.1:5000/recipes/5160756d96cc62079cc2db16,chowdown0
# Prioritises recipe IDs over ingredients
@app.route("/recipes", methods = ["GET"])
@app.route("/recipes/<recipe_ids>", methods = ["GET"])
def get_db_recipe(recipe_ids = "", page_size = 80, page_number = 1):
    l_ing = ""
    if request.url_rule.rule == "/recipes" and "ingredients" in request.args:
        l_ing = request.args.get("ingredients")

    if "page_size" in request.args:
        try:
            page_size = int(request.args.get("page_size"))
        except ValueError:
            pass
    if "page_number" in request.args:
        try:
            page_number = int(request.args.get("page_number"))
        except ValueError:
            pass

    if recipe_ids or (not l_ing and not recipe_ids):
        from bson.objectid import ObjectId

        db, find_filter, recipes = connect_db(), {}, []
        if recipe_ids:
            recipe_ids = recipe_ids.strip().split(",")
            find_filter = {"_id" : {"$in" : [ObjectId(ri) for ri in recipe_ids]}}
        cursor = db.recipes.find(find_filter).skip((page_number - 1) * page_size).limit(page_size)
        for doc in cursor:
            doc["_id"] = {"$oid" : str(doc.pop("_id"))}
            recipes.append(doc)
    else:
        tmp = set()
        for i, ing in enumerate(l_ing.strip().lower().split(",")):
            ing = ing.strip()
            if i == 0:
                tmp = set(ing_rcps[ing])
            else:
                tmp = tmp.intersection(ing_rcps[ing])
        tmp = [t for c, t in sorted([(rcp_ings[t], t) for t in tmp], key = lambda tup: tup[0])]
        recipes = loads(get_db_recipe(",".join(tmp), page_size, page_number)[0])["result"]

    return dumps({"result" : recipes, "size" : len(recipes)}), 200

# GET    - Returns recipes that are within searched category
# e.g. http://127.0.0.1:5000/categories?category=christmas&page_size=80&page_number=2
@app.route("/categories", methods = ["GET"])
def handle_categories():
    startRange = 0
    page_size = 80
    if "page_size" in request.args:
        try:
            page_size = int(request.args.get("page_size"))
        except ValueError:
            page_size = 80
    if "page_number" in request.args:
        try:
            startRange = int(request.args.get("page_number")) * page_size
        except ValueError:
            startRange = 0
    if "category" not in request.args:
        return dumps({"result" : "missing category parameter"}), 400
    else:
        cat = request.args.get("category").strip().lower()

    db, regx = connect_db(), re.compile(cat, re.IGNORECASE)
    count = db.recipes.find({"collectionName": regx}).count()
    res = list(db.recipes.find({"collectionName": regx}).skip(startRange).limit(page_size))
    for doc in res:
        doc["_id"] = {"$oid" : str(doc.pop("_id"))}

    return dumps({"result" : res, "size" : count}), 200

# POST    - creates new user
# PUT     - updates user details.
# DELETE  - deletes user
@app.route("/users", methods = ["POST", "PUT", "DELETE"])
def handle_users():
    sc = 1
    db = connect_db()
    if request.method == "POST":
        try:
            email = request.get_json()["email"]
            password = request.get_json()["password"]
            fName = request.get_json()["first_name"]
            lName = request.get_json()["last_name"]
            # check email is unique
            print(db.users.find({'email': email}).count())
            if db.users.find({'email': email}).count() != 0:
                return dumps({"error": "Already signed up with this email."}), 401, {"ContentType": "application/json"}
        except:
            return dumps({"error": "Need: email, password, first_name, last_name"}), 401, {"ContentType": "application/json"}
        sc = db.users.insert({"email": email, "password": password, "first_name": fName, "last_name": lName})
        session.pop("email", None)
        session["email"] = email
    else:
        # Following methods require user to be logged in
        if not "email" in session:
            return dumps({"error": "You need to be logged in first."}), 401, {"ContentType": "application/json"}
        currEmail = session["email"]

        if request.method == "DELETE":
            sc = db.users.remove({"email": currEmail})
            sc = db.favourites.remove({"email": currEmail})
            logout()
        elif request.json is None:
            return dumps({"error": "No valid JSON not provided"}), 400, {"ContentType": "application/json"}
        elif request.method == "PUT":
            try:
                email = request.get_json()["email"]
                password = request.get_json()["password"]
                fName = request.get_json()["first_name"]
                lName = request.get_json()["last_name"]
            except:
                return dumps({"error": "Need: email, password, first_name, last_name"}), 401, {"ContentType": "application/json"}

            query = {}
            if email:
                query["email"] = email
            if password:
                query["password"] = password
            if fName:
                query["first_name"] = fName
            if lName:
                query["last_name"] = lName

            sc = db.users.update({"email": currEmail}, query)
    if sc:
        return dumps({"success": True}), 200, {"ContentType": "application/json"}
    else:
        return dumps({"error": "Database operation failed. Check console"}), 401, {"ContentType": "application/json"}

# GET     - returns all favourited recipes for this user
# POST    - creates new favourite for a logged in user
# DELETE  - deletes specified favourite
@app.route("/favourites", methods = ["GET", "POST"])
@app.route("/favourites/<recipe_id>", methods = ["DELETE"])
def handle_favourites(recipe_id = ""):
    # check if user is logged in first
    if not 'email' in session:
        return dumps({"error": "You need to be logged in first."}), 401, {"ContentType": "application/json"}
    currEmail = session["email"]
    db = connect_db()
    if request.method == "GET":
        cursor = db.favourites.find({"email": currEmail})
        json_docs = []

        for fav_doc in cursor:
            response = get_db_recipe(fav_doc["recipe_id"])
            json_response = loads(response[0])
            recipe = json_response["result"][0]
            json_docs.append(recipe)

        return dumps({"result" : json_docs, "size" : len(json_docs)}), 200, {"ContentType": "application/json"}
    elif request.json is None:
        abort(400, 'No valid JSON not provided')
    elif request.method == "POST":
        recipe_id = request.get_json()['recipe_id']
        sc = db.favourites.insert({"email": currEmail, "recipe_id": recipe_id})
    elif request.method == "DELETE":
        sc = db.favourites.delete_many({"email": currEmail, "recipe_id":recipe_id})

    if sc:
        return dumps({"success": True}), 200, {"ContentType": "application/json"}
    else:
        return dumps({"error": "Database operation failed. Check console"}), 401, {"ContentType": "application/json"}

if __name__ == '__main__':
    if not exists(resdir):
        makedirs(resdir)

    get_ingredient_refence()
    # get_recipes() # un-comment it to rebuild database, extremely expensive process, just don't do it

    # check if indexing files are available for ingredient scraping
    if not isfile(resdir + "ing_rcps") or not isfile(resdir + "rcp_ings"):
        ing_rcps, rcp_ings = scrape_ingredients()
    else:
        with open(resdir + "ing_rcps", encoding = 'utf-8') as f1,\
             open(resdir + "rcp_ings", encoding = 'utf-8') as f2:
            ing_rcps = loads((''.join(f1.readlines())).strip())
            rcp_ings = loads((''.join(f2.readlines())).strip())

    app.run()