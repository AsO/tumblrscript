#!/usr/bin/env python
# -*- coding: utf-8 -*-

import urlparse
import oauth2 as oauth
import simplejson
import urllib
import netrc
import re
import ConfigParser
from argparse import ArgumentParser

usage = "usage: %prog [options]"

consumer_key, consumer_secret = None, None
xauth_token, xauth_token_secret = None, None

ini = ConfigParser.SafeConfigParser()
if ini.read('xauth.ini'):
    if ini.has_option('consumer', 'key'):
        consumer_key = ini.get('consumer', 'key')
    if ini.has_option('consumer', 'secret'):
        consumer_secret = ini.get('consumer', 'secret')
    if ini.has_option('xauth', 'token'):
        xauth_token = ini.get('xauth', 'token')
    if ini.has_option('xauth', 'token_secret'):
        xauth_token_secret = ini.get('xauth', 'token_secret')


class Post(object):

    @staticmethod
    def parse(parent, json):
        post = {
            'text': Text,
            'photo': Photo,
            'quote': Quote,
            'link': Link,
            'chat': Chat,
            'audio': Audio,
            'video': Video
        }[json['type']](parent, json)

        # post.data['state']
        post.json = json
        post.data['tags'] = ','.join(json['tags'])
        post.id = json['id']
        post.reblog_key = json['reblog_key']
        post.post_url = json['post_url']
        # post.data['tweet']
        # post.data['date']
        # post.data['slug']

        return post

    def __init__(self, parent):
        self.data = {}
        self.parent = parent

    def publish(self):
        self.data['state'] = 'published'
        self.data['id'] = self.id

        url = 'http://api.tumblr.com/v2/blog/%s/post/edit' % (self.parent.name)

        client = build_oauth_client()
        resp, content = client.request(url, method='POST', body=urllib.urlencode(self.data))

        json = simplejson.loads(content)
        if json['meta']['msg'] == 'OK':
            return True
        return False

    def like(self):
        client = build_oauth_client()
        url = 'http://api.tumblr.com/v2/user/like'
        resp, content = client.request(url, method='POST', body='id=%d&reblog_key=%s' % (self.id, self.reblog_key))

        json = simplejson.loads(content)
        if json['meta']['msg'] == 'OK':
            return True
        elif json['meta']['status'] == "404":
            # reblog key が使用できない場合は 404 が帰ってきます
            return False
        return False

    def unlike(self):
        client = build_oauth_client()
        url = 'http://api.tumblr.com/v2/user/unlike'
        resp, content = client.request(url, method='POST', body='id=%d&reblog_key=%s' % (self.id, self.reblog_key))

        json = simplejson.loads(content)
        if json['meta']['msg'] == 'OK':
            return True
        return False


class Text(Post):
    def __init__(self, tumblelog, json):
        super(Text, self).__init__(tumblelog)

        self.data['type'] = 'text'

        alias = {'title': 'title', 'body': 'body'}
        self.data.update(pickup_aliases(json, alias))


class Photo(Post):
    def __init__(self, tumblelog, json):
        super(Photo, self).__init__(tumblelog)

        self.data['type'] = 'photo'

        # FIXME: photo set にも対応させる
        alias = {'caption': 'caption', 'link_url': 'link'}
        self.data.update(pickup_aliases(json, alias))


class Quote(Post):
    def __init__(self, tumblelog, json):
        super(Quote, self).__init__(tumblelog)

        self.data['type'] = 'quote'

        alias = {'text': 'quote', 'source': 'source'}
        self.data.update(pickup_aliases(json, alias))


class Link(Post):
    def __init__(self, tumblelog, json):
        super(Link, self).__init__(tumblelog)

        self.data['type'] = 'link'

        alias = {'title': 'title', 'url': 'url', 'description': 'description'}
        self.data.update(pickup_aliases(json, alias))


class Chat(Post):
    def __init__(self, tumblelog, json):
        super(Chat, self).__init__(tumblelog)

        self.data['type'] = 'chat'

        alias = {'title': 'title', 'body': 'conversation'}
        self.data.update(pickup_aliases(json, alias))


class Audio(Post):
    def __init__(self, tumblelog, json):
        super(Audio, self).__init__(tumblelog)

        self.data['type'] = 'audio'

        alias = {'caption': 'caption'}
        self.data.update(pickup_aliases(json, alias))
        # self.data['external_url']


class Video(Post):
    def __init__(self, tumblelog, json):
        super(Video, self).__init__(tumblelog)

        self.data['type'] = 'video'

        alias = {'caption': 'caption'}
        self.data.update(pickup_aliases(json, alias))


class Tumblelog(object):

    def __init__(self, tumblelog):
        self.name = tumblelog
        self.posts = []

    def info(self, tumblelog=None):
        client = build_oauth_client()
        if tumblelog == None:
            tumblelog = self.name
        url = "http://api.tumblr.com/v2/blog/%s/info?api_key=%s" % (tumblelog, consumer_key)
        resp, content = client.request(url, method='GET')

        self.content = content
        self.json = simplejson.loads(content)

        self.msg = self.json['meta']['msg']
        self.status = self.json['meta']['status']

        return self.json

    def getpost(self, post_url):
        m = re.match('http://([^/]+)/post/(\d+)', post_url)
        tumblelog, post_id = m.group(1), m.group(2)
        url = "http://api.tumblr.com/v2/blog/%s/posts?api_key=%s&id=%s" % (
            tumblelog, consumer_key, post_id)

        client = build_oauth_client()
        resp, content = client.request(url, method='GET')

        self.content = content
        self.json = simplejson.loads(content)

        self.msg = self.json['meta']['msg']
        self.status = self.json['meta']['status']

        self.post = Post.parse(self, self.json['response']['posts'][0])

        return self.posts

    def likes(self, offset=0, limit=20):
        client = build_oauth_client()
        url = "http://api.tumblr.com/v2/user/likes?offset=%d&limit=%d" % (offset, limit)
        resp, content = client.request(url, method='GET')

        self.content = content
        self.json = simplejson.loads(content)

        self.msg = self.json['meta']['msg']
        self.status = self.json['meta']['status']

        self.liked_count = self.json['response']['liked_count']

        self.posts = []
        for post in self.json['response']['liked_posts']:
            self.posts.append(Post.parse(self, post))

        return self.posts

    def drafts(self):
        client = build_oauth_client()
        url = 'http://api.tumblr.com/v2/blog/%s/posts/draft' % (self.name)
        resp, content = client.request(url, method='GET')

        self.content = content
        self.json = simplejson.loads(content)

        self.msg = self.json['meta']['msg']
        self.status = self.json['meta']['status']

        self.posts = []
        for post in self.json['response']['posts']:
            self.posts.append(Post.parse(self, post))

        return self.posts

def load_netrc():
    global consumer_key, consumer_secret, \
           xauth_token, xauth_token_secret
    nrc = netrc.netrc()
    consumer_key, _, consumer_secret = nrc.authenticators('tumblr_consumer')
    xauth_token, _, xauth_token_secret = nrc.authenticators('tumblr_xauth_token')


def posts_from_content(content):
    json = simplejson.loads(content)
    posts = []
    if 'posts' in self.json['response']:
        for post in json['response']['posts']:
            posts.append(Post.parse(self, post))
    elif 'liked_posts' in self.json['response']:
        for post in json['response']['liked_posts']:
            posts.append(Post.parse(self, post))
    return posts


def build_oauth_client():
    consumer = oauth.Consumer(consumer_key, consumer_secret)
    token = oauth.Token(xauth_token, xauth_token_secret)
    client = oauth.Client(consumer, token)
    client.set_signature_method = oauth.SignatureMethod_HMAC_SHA1()
    return client
    # この関数で使うかも知れないし使わないかも知れないパラメータの設定
    # params['x_auth_mode'] = 'client_auth'
    # params['oauth_version'] = '1.0a'


def pickup_aliases(src, aliases):
    results = {}
    for alias_from, alias_to in aliases.iteritems():
        if alias_from in src:
            if src[alias_from]:
                results[alias_to] = src[alias_from].encode('UTF-8')
    return results


def arg_parsing():
    # prog 1st-command 2nd-command という形を取る
    parser = ArgumentParser()

    choice_fetch = ['drafts', 'relike']
    choice_command = ['publish']

    parser.add_argument("fetch", choices=choice_fetch, help=u"ポストの読み込みタイプか特殊なコマンド")
    parser.add_argument("command", nargs='?', choices=choice_command, help=u"読み込んだポストの処理法")
    parser.add_argument("-t", "--tumblelog", dest="tumblelog", help=u"ターゲットのTumblelogを指定します")
    parser.add_argument("-O", "--save", dest="content_file", default=None,
                        help=u"APIで取得したテキストを全て保存します")
    parser.add_argument("--retry-delay", dest="delay", type=float, default=1,
                        help=u"失敗時に遅延する秒数を指定します")
    parser.add_argument("-r", "--reverse", action="store_true",
                        help=u"ポストへのコマンドを逆順に処理する")
    parser.add_argument("-c", "--count", dest="count", type=int, default=30,
                        help=u"各ステップで一度に処理するポスト数")
    parser.add_argument("-m", "--max-count", dest="max", type=int,
                        help=u"全ステップを通して処理するポスト数")
    parser.add_argument("-s", "--step-time", dest="second", type=float, default=600,
                        help=u"各ステップ間の秒数")
    parser.add_argument("-n", "--netrc", action="store_true",
                        help=u"認証情報を .netrc を元に構築します。")

    args = parser.parse_args()
    return args


def cmd_relike(args, t):
    # FIXME: relike は動作確認をしていません
    tempfile = __import__('tempfile')
    fn = tempfile.mktemp()

    t.likes(0, 1)
    liked_count = t.liked_count

    f = open(fn, 'w')
    fail_unlikes = []  # unlike が必ず失敗するポストが溜まって無限ループに陥るのを防ぎます
    for i in xrange(0, (liked_count - 1 / 20.0) + 1):
        posts = t.likes(len(fail_unlikes), 20)
        for post in posts:
            if not post.unlike():
                fail_unlikes.append(post)
        f.write(t.content)
        f.write('\n')
    f.close()
    del fail_unlikes

    f = open(fn, 'r')
    fail_likes = []  # like fail は致命的なため確保しておきます
    for line in f:
        posts = posts_from_content(line)
        for post in posts:
            if not post.like():
                fail_likes.append(post)
    f.close()

    print 'Failed likes:'
    for post in fail_likes:
        print post.post_url


def cmd_publish(args, posts):
    time = __import__('time')
    len_posts = len(posts)
    posts_seq = [posts[i:i + args.count] for i in xrange(0, len(posts), args.count)]

    print "start to publish %d posts." % (len_posts)

    i = 0
    next_time = time.time()
    for posts in posts_seq:
        while next_time >= time.time():
            print "\rWait: %3f sec" % (next_time - time.time()),
            time.sleep(0.0005)
        next_time = time.time() + args.second
        for post in posts:
            i += 1
            print '\r[%d/%d] publish: %d ...' % (i, lne_posts, post.id),
            if post.publish():
                print 'OK'
            else:
                print 'Fail'


def main():
    args = arg_parsing()

    if args.netrc:
        load_netrc()

    if not args.tumblelog:
        tumblelog = raw_input('Input tumblelog: ')
        t = Tumblelog(tumblelog)
    else:
        t = Tumblelog(args.tumblelog)

    # 特殊コマンド
    if args.fetch == 'relike':
        cmd_relike(args, t)
        return

    # posts を取得する
    posts = []
    if args.fetch == 'dashboard':
        pass  # 現在この機能を追加する予定はありません
    elif args.fetch == 'posts':
        pass  # 現在この機能を追加する予定はありません
    elif args.fetch == 'drafts':
        posts = t.drafts()
    elif args.fetch == 'likes':
        pass  # 現在この機能を追加する予定はありません
    else:
        return

    # post に対するオプションがあれば先に処理をしておく
    if args.reverse:
        posts = posts[::-1]
    if args.max:
        posts = posts[:args.max]

    # posts を処理する
    if args.command == 'like':
        pass  # 現在この機能を追加する予定はありません
    elif args.command == 'publish':
        cmd_publish(args, posts)
    else:
        pass
    return


if __name__ == '__main__':
    main()