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
            remove_hyperlink = BeautifulSoup(str(soup1.find("div", tag_filter).p), "lxml")
            for a in remove_hyperlink.findAll('a'):
                a.replaceWithChildren()
            d["description"] = "".join(remove_hyperlink.p.contents)
            tag_filter = {"itemprop" : "ingredient"}
            d["ingredients"] = "\n".join([ing.p.contents[0]
                                          for ing in soup1.find_all("li", tag_filter)])
            with open(resdir + fname, "a") as f:
                f.write(str(d).replace("'", "\"") + "\n")

    if not exists(resdir):
        makedirs(resdir)
    get_openrecipes()
    get_chowdown()

def get_ingredients():
    from json import loads
    from nltk.tag import pos_tag
    from os import listdir
    from os.path import isfile
    import re

    units = ""
    with open(resdir + "units", "r") as f:
        units = "(" + "|".join([line.rstrip() for line in f]) + ")"
    num_frac = "[\u2215\u2189\u2150-\u215f\u2044\u2010-\u2015\u00bc-\u00be\u002d-\u0039]"
    quantity_filter = "([\d]+\s*x\s+)*(((" + num_frac\
                                           + "|\s+to\s+)\s*)+("\
                                           + units\
                                           + "(\s+(of\s+)*|\s*[\u2215\u2044\u2010-\u2015\u002c-\u002f]s*))*)+"
    l_ing = set()
    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname) as f:
            for line in f.readlines():
                for ing in loads(line)["ingredients"].lower().strip().split("\n"):
                    # below is a sequence of filters
                    ing = re.sub("\(.*?\)", "", ing) # removes between ()
                    ing = re.sub("\(.*", "", ing) # removes ( and after
                    ing = re.compile(r"" + quantity_filter, flags = re.IGNORECASE).sub("", ing)
                    ing = re.sub("^\s*" + units + "\s*$", "", ing)
                    ing = re.sub("^\s*(x|X)\s+", "", ing)
                    l_ing.add(ing.strip())

    l_ing2 = set()
    for ing in l_ing:
        for elem in re.split("\u0021|\u0025|[\u002a-\u002c\u003a-\u003b]|\u007e|\s+(or|and|of|for)\s+|&amp", ing):
            # TODO add spelling corrections to ingredients before removing non-NN's
            if not elem:
                continue
            s = ""
            for tag in pos_tag(elem.split()):
                if re.match("NNS*", tag[1]) and not re.match("^" + units + "$", tag[0]):
                    s += tag[0] + " "
            l_ing2.add(s.strip())
    print(l_ing2)
    print(len(l_ing2))

if __name__ == '__main__':
    get_recipes()
    get_ingredients()
    app.run()

# nltk.download('averaged_perceptron_tagger')
# 54838