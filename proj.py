from flask import jsonify, Flask, request, Response
from os import makedirs, remove
from os.path import dirname, exists, isfile, realpath
from shutil import copyfileobj

app = Flask(__name__)
resdir = dirname(realpath(__file__)) + "/resources/"

@app.route("/", methods=['Get'])
def greet():
    return "Hi!"

def get_openrecipe():
    from os import chdir
    from wget import download
    import gzip

    fname = "20170107-061401-recipeitems.json"
    if not isfile(resdir + fname):
        chdir(resdir)
        download("https://s3.amazonaws.com/openrecipes/" + fname + ".gz")
        with gzip.open(fname + ".gz", 'rb') as f_in:
            with open(fname, 'wb') as f_out:
                copyfileobj(f_in, f_out)

if __name__ == '__main__':
    if not exists(resdir):
        makedirs(resdir)
    get_openrecipe()

    app.run()