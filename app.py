import json
from datetime import datetime
from flask import Flask, render_template, jsonify, send_from_directory

app = Flask(__name__)
dataset = json.load(open('data/dataset.json', 'r'))


@app.template_filter('tsformat')
def format_timestamp(ts):
    return datetime.fromtimestamp(ts)


@app.route('/')
def index():
    return render_template('overview.html', data=dataset.values())


@app.route('/map')
def map():
    # TODO this is having trouble rendering all the images
    return render_template('map.html', data=dataset.values())


@app.route('/data.json')
def data():
    data = list(dataset.values())
    return jsonify(data=data)


@app.route('/thumbs/<id>')
def thumb(id):
    image = dataset[id]
    lid = image['usages'][0]['lid']
    return send_from_directory('thumbs/pol', lid)


@app.route('/image/<id>')
def image(id):
    image = dataset[id]
    ancestors, descendants = [], []
    for rel in image['relatives']:
        id = str(rel['id'])
        im = dataset[id]
        if im['usages'][0]['timestamp'] < image['usages'][0]['timestamp']:
            ancestors.append((im, rel['dist']))
        else:
            descendants.append((im, rel['dist']))
    image['genealogy'] = {
        'ancestors': ancestors,
        'descendants': descendants
    }
    return render_template('image.html', image=image)


if __name__ == '__main__':
    app.run(debug=True)