from flask import Flask, request, Response
from os.path import dirname, realpath

app = Flask(__name__)
resdir = dirname(realpath(__file__)) + "/resources/"

@app.route("/", methods=['Get'])
def greet():
    return "Hi!"

def get_recipes():
    from bs4 import BeautifulSoup
    from datetime import datetime
    from os import makedirs
    from os.path import exists, isfile
    from requests import get
    from time import time

    def revert_cooking_abbr(ing_str: str):
        return ing_str.replace("tsp", "teaspoon")\
                      .replace("tbsp", "tablespoon")\
                      .replace("tbs", "tablespoon")

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
            d = {"_id" : {"$oid" : i},
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
            remove_descr_hyperlink = BeautifulSoup(str(soup1.find("div", tag_filter).p), "lxml")
            for a in remove_descr_hyperlink.findAll('a'):
                a.replaceWithChildren()
            d["description"] = "".join(remove_descr_hyperlink.p.contents)
            tag_filter = {"itemprop" : "ingredient"}
            d["ingredients"] = "\n".join([revert_cooking_abbr(ing.p.contents[0])
                                         for ing in soup1.find_all("li", tag_filter)])
            with open(resdir + fname, "a") as f:
                f.write(str(d).replace("'", "\"") + "\n")

    if not exists(resdir):
        makedirs(resdir)
    get_openrecipes()
    get_chowdown()

def get_ingredients():
    from json import loads
    from os import listdir
    from os.path import isfile

    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname) as f:
            content = [loads(l) for l in f.readlines()]
            print(len(content))

if __name__ == '__main__':
    get_recipes()
    get_ingredients()
    app.run()