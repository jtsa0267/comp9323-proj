from bs4 import BeautifulSoup
from flask import Flask, request, Response
from os.path import dirname, isfile, realpath
from os.path import exists
from requests import get
import json
import pymongo
from pymongo import MongoClient

app = Flask(__name__)
resdir = dirname(realpath(__file__)) + "/resources/"

@app.route("/", methods=['Get'])
def greet():
    db=connect_db()
    # print(recipes.find_one({"name": "Hot Roast Beef Sandwiches"}))
    import re
    # regx = re.compile("beef", re.IGNORECASE)
    # res=db.recipe.find_one({"name": regx})


    regx = re.compile("Sandwich", re.IGNORECASE)
    res=db.recipe.find_one({"ingredients": regx})

    print(res)

    # cursor=db.recipe.find({'name':'/beef/i'})
    # for document in cursor:
    #     print(document)
    # db.users.find().forEach(function(myDoc) {print("user: " + myDoc.name)} )
    return "Hi!"

def connect_db():
    DB_NAME = "comp9323"
    DB_HOST = "ds251112.mlab.com"
    DB_PORT = 51112
    DB_USER = "admin"
    DB_PASS = "admin18"
    pass

    connection = MongoClient(DB_HOST, DB_PORT)
    db = connection[DB_NAME]
    db.authenticate(DB_USER, DB_PASS)
    # print(db.collection_names())
    return db

@app.route("/insert_recipes", methods=['Get'])
def insert_recipes():

@app.route("/insert_recipes", methods=['Get'])
def insert_recipes():
    db=connect_db()
    ###note: removed '$' from oid and date variables
    #TODO: change to load foreach file in folder
    with open('resources/input_file.txt', 'rb') as f:
        for row in f:
            db.recipe.insert(json.loads(row))

def get_ingredient_refence():
    from re import match, sub
    from textblob.inflect import singularize

    fname = "ing_list"
    if isfile(resdir + fname):
        return
    oxfordreference_base_url = "http://www.oxfordreference.com/view/10.1093/acref/9780199234875.001.0001/acref-9780199234875"
    tag_filter = {"class" : "contentItem oxencycl-entry locked hasCover chunkResult hi-visible py-3 border-top flex flex-row"}
    i, ing_list = 1, []
    while True:
        soup = BeautifulSoup(get(oxfordreference_base_url + "?page=" + str(i) + "&pageSize=100").text, "lxml")
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
                    if len(ing) > 2 and not ing.startswith("free ") and not match("^.*[A-Z].*$", ing) and\
                    not match("^.*[\u2010-\u2015\-]$", ing):
                        ing = sub("\(.*\)", "", ing).strip()
                        if not ing:
                            continue
                        ing_split = ing.split(" ")
                        ing_list.append(' '.join(ing_split[: -1]) + " " + singularize(ing_split[-1]))
        i += 1
    with open(resdir + fname, "w") as f:
        for t in sorted(ing_list):
            f.writelines(t + "\n")

def get_recipes():
    from bs4 import BeautifulSoup
    from datetime import datetime
    from os import makedirs
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

    def get_chowdown():
        fname = "chowdown-recipes.json"
        if isfile(resdir + fname):
            return
        chowdown_base_url = "http://chowdown.io"
        soup = BeautifulSoup(get(chowdown_base_url).text, "lxml")
        tag_filter = {"class" : "sm-col sm-col-6 md-col-6 lg-col-4 xs-px1 xs-mb2"}
        for i, tag in enumerate(soup.find_all("div", tag_filter)):
            url = chowdown_base_url + tag.a.attrs["href"]
            soup1 = BeautifulSoup(get(url).text, "lxml")
            d = {"_id" : {"oid" : i},
                 "name" : soup1.title.contents[0],
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
            tag_filter = {"itemprop" : "ingredient"}
            d["ingredients"] = "\n".join([ing.p.contents[0]
                                          for ing in soup1.find_all("li", tag_filter)])
            with open(resdir + fname, "a") as f:
                f.write(str(d).replace("'", "\"") + "\n")

    get_openrecipes()
    get_chowdown()

def get_ingredients():
    from json import loads
    from nltk.corpus import wordnet
    from nltk.tokenize import word_tokenize
    from os import listdir
    from os.path import isfile
    from textblob import TextBlob
    import re

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

    units_regex, units_set, l_ing, ings = "", set(), set(), set()
    with open(resdir + "units", "r") as f:
        tmp = [line.rstrip() for line in f]
        units_regex = re.sub("(\.|\#)", r"\\\1", "|".join(tmp))
        units_set = set(tmp)
    quantity_filter = "[\u2150-\u215e\u00bc-\u00be\u0030-\u0039]\s*("\
                          + units_regex + ")*(\s*\)\s*of\s+|\s+of\s+|\s*\)\s*|\s+)"\
                          + "([\u24C7\u2122\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u01bf\u01cd-\u02af\u0061-\u007a\ \-]{2,})"
    with open(resdir + "ing_list", "r", encoding='utf-8') as f:
        ings = set([line.strip() for line in f])
    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname, encoding='utf-8') as f:
            for k, line in enumerate(f.readlines()):
                print(k)
                for ing in re.split("\n|,", loads(line)["ingredients"].lower().strip()):
                    ing = re.findall(quantity_filter, ing)
                    if not ing or len(ing) > 1:
                        continue
                    for elem in re.split("\s+(and|or|with|in)\s+", ing[0][-1].strip()):
                        s, tokens = "", reversed(word_tokenize(elem))
                        for i, token in enumerate(tokens):
                            token = token.rstrip()
                            if not token or re.match("^[a-z]+([\u002d\u2010-\u2015][a-z]+)+$", token):
                                continue
                            # if token not in ings and not wordnet.synsets(token):
                            #     token = symspell_correction(token)
                            if i == 0:
                                token = TextBlob(token).words
                                if not token:
                                    continue
                                token = token[0].singularize()
                            if token not in ings or token in units_set:
                                continue
                            else:
                                s = token
                            for j in range(i + 1, len(list(tokens))):
                                tmp = " ".join(reversed(list(tokens)[i + 1 : j + 1]))
                                if not tmp + " " + s in ings:
                                    s = " ".join(reversed(list(tokens)[i + 1 : j])) + " " + s
                                    break
                            break
                        s = s.strip()
                        if s and len(s) > 2:
                            l_ing.add(s.strip())
    print(l_ing)
    print(len(l_ing))

if __name__ == '__main__':
    if not exists(resdir):
        makedirs(resdir)
    get_ingredient_refence()
    exit()
    get_recipes()
    get_ingredients()
    connect_db()
    app.run()
# nltk.download('punkt')
# 1137