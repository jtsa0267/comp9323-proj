from bs4 import BeautifulSoup
from flask import Flask, request, Response
from os.path import dirname, isfile, realpath
from requests import get

app = Flask(__name__)
resdir = dirname(realpath(__file__)) + "/resources/"

@app.route("/", methods=['Get'])
def greet():
    return "Hi!"

def get_ingredient_refence():
    from textblob.inflect import singularize

    def oxford_reference_ing():
        from re import match, sub

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
                        not match("^.*[A-Z].*$", ing) and not match("^.*[\u2010-\u2015\-]$", ing):
                            ing = sub("\(.*\)", "", ing).strip()
                            if not ing:
                                continue
                            ing_split = ing.split(" ")
                            ing_list.append((' '.join(ing_split[: -1]) + " " + singularize(ing_split[-1])).strip())
            i += 1

        return ing_list

    def wiki_cookbook_ing():
        from bs4 import Comment
        from re import sub

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
                        ing = sub("\(.*\)", "", ing).strip()
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

def get_recipes():
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

    get_openrecipes()
    get_chowdown()

def get_ingredients():
    from json import loads
    from nltk.corpus import wordnet
    from os import listdir
    from os.path import isfile
    from textblob.inflect import singularize
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
        tmp = [line.strip() for line in f]
        units_regex = re.sub("(\.|\#)", r"\\\1", "|".join(tmp))
        units_set = set(tmp)
    quantity_filter = "[\u2150-\u215e\u00bc-\u00be\u0030-\u0039]\s*("\
                          + units_regex + ")*(\s*\)\s*of\s+|\s+of\s+|\s*\)\s*|\s+)"\
                          + "([\u24C7\u2122\u00c0-\u00d6\u00d8-\u00f6\u00f8-\u01bf\u01cd-\u02af\u0061-\u007a\ \-]{2,})"
    with open(resdir + "ing_list", "r") as f:
        ings = set([line.strip() for line in f])
    for fname in listdir(resdir):
        if not isfile(resdir + fname) or not fname.endswith(".json"):
            continue
        with open(resdir + fname) as f:
            for k, line in enumerate(f.readlines()):
                # print(k)
                for ing_str in re.split("\n|,", loads(line)["ingredients"].lower().strip()):
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
                            l_ing.add(ing.strip())
    print(sorted(list(l_ing)))
    print(len(l_ing))

if __name__ == '__main__':
    from os.path import exists

    if not exists(resdir):
        makedirs(resdir)
    get_ingredient_refence()
    # exit()
    get_recipes()
    get_ingredients()
    app.run()

# 1298