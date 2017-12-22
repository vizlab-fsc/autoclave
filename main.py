import io
import os
import json
import random
import requests
import tempfile
import imagehash
import numpy as np
import networkx as nx
from PIL import Image
from tqdm import tqdm
from lib.domains import chan
from lib.image import resize_to_limit
from sklearn.manifold import TSNE
from sklearn.decomposition import PCA
from scipy.spatial.distance import pdist, squareform

HASH_SIZE = 8 # must be power of 2
c = chan.FourChan('pol')


def get_media_link(id):
    resp = requests.get('http://archive.4plebs.org/_/api/chan/post/', params={'board':'pol','num':id})
    data = resp.json()
    return data['media']['media_link']


def sample_posts(sample_size):
    # only keep posts with attachments
    print('sampling posts...')
    sample = {}
    threads = os.listdir('data/pol')
    threads = random.sample(threads, sample_size)
    for id in tqdm(threads):
        fname = os.path.join('data/pol', id)
        thread = json.load(open(fname, 'r'))
        posts = [c.parse_post(post) for post in thread['posts']]
        for p in posts:
            if not p['attachments']:
                continue
            p['thread_id'] = id
            sample[p['lid']] = p
    return sample


def get_image_urls(post_ids):
    print('getting image urls...')
    image_urls = {}
    for lid in tqdm(post_ids):
        image_urls[lid] = get_media_link(lid)
    return image_urls


def download_image(fname, url):
    """downloads a remote image to a PIL Image"""
    buffer = tempfile.SpooledTemporaryFile(max_size=1e9)
    res = requests.get(url, stream=True)
    if res.status_code == 200:
        for chunk in res:
            buffer.write(chunk)
        buffer.seek(0)
        try:
            img = Image.open(io.BytesIO(buffer.read()))
            img.save(fname, format=img.format)
        except OSError:
            print(url)
            raise
    else:
        print('non-200 status for:', url)
        # res.raise_for_status()


def compute_hashes(images):
    print('computing hashes...')
    hashes = {}
    for lid in tqdm(images):
        fname = os.path.join('img/pol', lid)
        try:
            img = Image.open(fname)
            hash = imagehash.phash(img, hash_size=HASH_SIZE)
            hashes[lid] = str(hash)
        except OSError:
            continue
    return hashes


def resize_images(images):
    for id in tqdm(images):
        fname = os.path.join('img/pol', id)
        tname = os.path.join('thumbs/pol', id)
        if os.path.exists(tname):
            continue
        try:
            img = Image.open(fname)
            img = resize_to_limit(img, (50, 50))
            img.save(tname, format='JPEG', quality=75, subsampling=0)
        except OSError:
            continue


def tsne_project(hashes):
    print('computing tsne...')
    # project to 2D space for the interface
    pca = PCA(n_components=50)
    v = pca.fit_transform(hashes)
    tsne = TSNE(n_components=2, verbose=2)
    v = tsne.fit_transform(v)

    tx, ty = v[:,0], v[:,1]
    tx = (tx-np.min(tx)) / (np.max(tx) - np.min(tx))
    ty = (ty-np.min(ty)) / (np.max(ty) - np.min(ty))

    positions = {}
    for (id, _), x, y in tqdm(zip(enumerate(hashes), tx, ty)):
        positions[id] = (x, y)
    return positions


def try_load(fname, fn, force=False):
    try:
        if force:
            raise FileNotFoundError
        data = json.load(open(fname, 'r'))
        changed = False
    except FileNotFoundError:
        data = fn()
        with open(fname, 'w') as f:
            json.dump(data, f)
        changed = True
    return data, changed


if __name__ == '__main__':
    sample_size = 5000

    # sample posts
    posts, changed = try_load(
        'data/post_sample.json', lambda: sample_posts(sample_size))
    post_ids = posts.keys()

    # get image urls for posts
    image_urls, changed = try_load(
        'data/image_urls.json', lambda: get_image_urls(post_ids), changed)

    # download images
    # print('downloading images...')
    # for name, url in tqdm(image_urls.items()):
    #     if any(url.endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
    #         fname = os.path.join('img/pol', name)
    #         if not os.path.exists(fname):
    #             download_image(fname, url)
    #             changed = True
    #     else:
    #         print('invalid extension:', url)

    # generate thumbnails
    print('generating thumbnails...')
    images = os.listdir('img/pol')
    resize_images(images)

    # compute hashes
    hashes, changed = try_load(
        'data/image_hashes.json', lambda: compute_hashes(images), changed)
    images = [(lid, hash) for lid, hash in hashes.items()]

    # find images that are the same
    print('finding ~identical images...')
    same_dist_thresh = 2.
    _, hashes = zip(*images)
    hashes = np.array([imagehash.hex_to_hash(h, hash_size=HASH_SIZE).hash.flatten() for h in hashes])
    dist_mat = squareform(pdist(hashes, metric='euclidean'))
    same_pairs = np.argwhere(dist_mat <= same_dist_thresh)
    same_pairs = [(a, b) for a, b in same_pairs if a != b]
    G = nx.Graph()
    G.add_edges_from(same_pairs)
    same_imgs = list(nx.connected_components(G))

    # assemble the dataset
    # maintain as a list for positional indexing
    # later we'll convert to a dict
    print('preparing dataset...')
    dataset = []
    to_process_ids = list(range(len(images)))
    for group in same_imgs:
        usages = []
        for i in group:
            lid, hash = images[i]
            posts[lid]['media_url'] = image_urls[lid]
            posts[lid]['hash'] = str(hash)
            usages.append(posts[lid])
            to_process_ids.remove(i)
        usages = sorted(usages, key=lambda u: u['timestamp'])
        dataset.append({
            'hash': usages[0]['hash'], # just using first hash
            'usages': usages,
            'relatives': []
        })
    for i in to_process_ids:
        lid, hash = images[i]
        posts[lid]['media_url'] = image_urls[lid]
        posts[lid]['hash'] = str(hash)
        usages = [posts[lid]]
        dataset.append({
            'hash': str(hash),
            'usages': usages,
            'relatives': []
        })

    # find relatives
    print('finding relatives...')
    related_dist_thresh = 3.
    hashes = np.array([imagehash.hex_to_hash(i['hash'], hash_size=HASH_SIZE).hash.flatten() for i in dataset])
    dist_mat = squareform(pdist(hashes, metric='euclidean'))
    relative_pairs = np.argwhere(dist_mat <= related_dist_thresh)
    for a, b in relative_pairs:
        if a != b:
            print((a, b))
            dataset[a]['relatives'].append({
                'id': int(b),
                'dist': float(dist_mat[a, b])
            })


    # compute tsne projection
    # positions, changed = try_load(
    #     'data/image_positions.json', lambda: tsne_project(hashes), changed)
    # for id, (x, y) in positions.items():
    #     dataset[int(id)]['x'] = x
    #     dataset[int(id)]['y'] = y

    # save dataset
    print('saving dataset...')
    for id, d in enumerate(dataset):
        d['id'] = id
    dataset = {i: d for i, d in enumerate(dataset)}
    with open('data/dataset.json', 'w') as f:
        json.dump(dataset, f)

    # generate tsne projection image
    # width, height = 4000, 3000
    # max_dim = 50
    # preview = Image.new('RGBA', (width, height))
    # for id, (x, y) in tqdm(positions.items()):
    #     img = dataset[int(id)]['usages'][0]['lid']
    #     tile = Image.open(os.path.join('img/pol', img))
    #     rs = max(1, tile.width/max_dim, tile.height/max_dim)
    #     tile = tile.resize((int(tile.width/rs), int(tile.height/rs)), Image.ANTIALIAS)
    #     preview.paste(tile, (int((width-max_dim)*x), int((height-max_dim)*y)), mask=tile.convert('RGBA'))
    # preview.save('data/tsne_preview.jpg')