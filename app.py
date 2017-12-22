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
    imgs = list(dataset.values())
    imgs = sorted(imgs, key=lambda im: im['usages'][-1]['timestamp'])
    most_used = max(imgs, key=lambda im: len(im['usages']))
    most_recent = imgs[-1]
    most_relatives = max(imgs, key=lambda im: len(im['relatives']))
    highlights = {
        'most used': most_used,
        'most recent': most_recent,
        'most relatives': most_relatives
    }
    earliest = min(imgs, key=lambda im: min(im['usages'], key=lambda u: u['timestamp'])['timestamp'])
    meta = {
        'start_ts': earliest['usages'][0]['timestamp'],
        'end_ts': most_recent['usages'][-1]['timestamp'],
        'n': len(imgs),
        'n_usages': sum(len(im['usages']) for im in imgs)
    }
    return render_template('overview.html', highlights=highlights, meta=meta)


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