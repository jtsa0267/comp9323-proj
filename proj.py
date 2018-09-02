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
    from nltk import PorterStemmer
    from nltk.tag import pos_tag
    from nltk.tokenize import word_tokenize
    from os import listdir
    from os.path import isfile
    from symspellpy.symspellpy import SymSpell, Verbosity
    import re

    def symspell_correction(ing_str):
        sym_spell = SymSpell(83000, 2)
        dictionary_path = dirname(realpath(__file__)) + "/symspellpy/frequency_dictionary_en_82_765.txt"
        if not sym_spell.load_dictionary(dictionary_path, 0, 1):
            return ""
        suggestions = sym_spell.lookup_compound(ing_str, 1)
        return sorted(suggestions, key = lambda x: x.count, reverse = False)[0].term

    units_regex, units_set, all_set, l_ing = "", set(), set(), set()
    with open(resdir + "units", "r") as f:
        tmp = [line.rstrip() for line in f]
        units_regex = re.sub("(\.|\#)", r"\\\1", "|".join(tmp))
        units_set = set(tmp)
    with open(resdir + "states", "r") as f:
        all_set = set([line.rstrip() for line in f]).union(units_set)
    quantity_filter = "[\u2150-\u215e\u00bc-\u00be\u0030-\u0039]\s*("\
                          + units_regex + ")*(\s*\)\s*of\s+|\s+of\s+|\s*\)\s*|\s+)"\
                          + "([\u24C7\u2122\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u01bf\u01cd-\u02af\u0061-\u007a\ \-]{2,})"
    descriptor_filter = "(^|\s+)[a-z]+([\u002d\u2010-\u2015][a-z]+)+($|\s+)"
    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname) as f:
            for k, line in enumerate(f.readlines()):
                print(k)
                for ing in re.split("\n|,", loads(line)["ingredients"].lower().strip()):
                    ing = re.findall(quantity_filter, ing)
                    if not ing or len(ing) > 1:
                        continue
                    # ing = re.sub("(^|\s+)[a-z]+\-[a-z]+($|\s+)", " ", ing)
                    # ing = symspell_correction(re.sub("^\s*x\s+", "", ing[0][-1].strip()))
                    ing = re.sub("^\s*(x|X)\s+", "", ing[0][-1].strip())
                    if not ing:
                        continue
                    for elem in re.split("\s+(and|or|with|in)\s+", ing):
                        s, j, tmp = "", -1, pos_tag(word_tokenize(elem))
                        for i, tag in enumerate(tmp):
                            if re.match("NNS*", tag[1]) and tag[0] not in all_set:
                                j = i
                                break
                        if j != -1:
                            if j != 0 and tmp[j - 1][1] == "JJ" and tmp[j - 1][0] not in all_set\
                                      and not re.match(descriptor_filter, tmp[j - 1][0][0]):
                                s = tmp[j - 1][0]
                            while tmp[j][1] == "NN" or tmp[j][1] == "NNS":
                                if tmp[j][0] in all_set or re.match(descriptor_filter, tmp[j][0]):
                                    j += 1
                                    if j == len(tmp):
                                        break
                                    else:
                                        continue
                                s += " " + str(PorterStemmer().stem(tmp[j][0]))
                                j += 1
                                if j == len(tmp):
                                    break
                        if s.strip() and len(s.strip()) > 1:
                            l_ing.add(s.strip())

    print(l_ing)
    print(len(l_ing))

if __name__ == '__main__':
    get_recipes()
    get_ingredients()
    app.run()

# nltk.download('punkt')
# 23488