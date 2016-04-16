import os
import re
import random
import hashlib
import hmac
from string import letters
from fileparser import parse_file, generate_url

import webapp2
import jinja2
from google.appengine.api import users
from google.appengine.ext import db
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader = jinja2.FileSystemLoader(template_dir),
                               autoescape = True)


secret = 'onepiece'


# -----------------------------------------------------------------------------
# define a user database 
class User(db.Model):
    name = db.StringProperty(required = True)
    pw_hash = db.StringProperty(required = True)
    email = db.StringProperty()

    @staticmethod
    def valid_pw(name, password, h):
        salt = h.split(',')[0]
        return h == User.make_pw_hash(name, password, salt)

    @staticmethod
    def make_pw_hash(name, pw, salt = None):
        if not salt:
            salt = User.make_salt()
        h = hashlib.sha256(name + pw + salt).hexdigest()
        return '%s,%s' % (salt, h)

    @staticmethod
    def make_salt(length = 5):
        return ''.join(random.choice(letters) for x in xrange(length))

    @staticmethod
    def users_key(group = 'default'):
        return db.Key.from_path('users', group)

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent = User.users_key())

    @classmethod
    def by_name(cls, name):
        user = User.all().filter('name =', name).get()
        return user

    @classmethod
    def register(cls, name, pw, email = None):
        pw_hash = User.make_pw_hash(name, pw)
        return User(parent = User.users_key(),
                    name = name,
                    pw_hash = pw_hash,
                    email = email)

    @classmethod
    def login(cls, name, pw):
        user = cls.by_name(name)
        if user and User.valid_pw(name, pw, user.pw_hash):
            return user


# -----------------------------------------------------------------------------
# base handler
class BaseHandler(webapp2.RequestHandler):

    def _check_secure_val(self, secure_val):
        val = secure_val.split('|')[0]
        if secure_val == self._make_secure_val(val):
            return val

    def _make_secure_val(self, val):
        return '%s|%s' % (val, hmac.new(secret, val).hexdigest())

    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render(self, templateFileName, **kw):
        self.write(self.render_template_with_user(templateFileName, **kw))

    def render_template_with_user(self, template, **params):
        params['user'] = self.user
        return self.render_template(template, **params)
     
    def render_template(self, templateFileName, **params):
        template = jinja_env.get_template(templateFileName)
        return template.render(**params)

    def set_secure_cookie(self, name, val):
        cookie_val = self._make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and self._check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))


# -----------------------------------------------------------------------------
# define a class for sign up      
class Signup(BaseHandler):

    USER_REGEX = re.compile(r"""^[a-zA-Z0-9_-]{3,20}$""")
    def _valid_username(self, username):
        return username and self.USER_REGEX.match(username)

    PASS_REGEX = re.compile(r"""^.{3,20}$""")
    def _valid_password(self, password):
        return password and self.PASS_REGEX.match(password)

    EMAIL_REGEX  = re.compile(r'''^[\S]+@[\S]+\.[\S]+$''')
    def _valid_email(self, email):
        return not email or self.EMAIL_REGEX.match(email)

    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username = self.username,
                      email = self.email)

        if not self._valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not self._valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
            
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not self._valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)

        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


# -----------------------------------------------------------------------------
# define a class for register page
class Register(Signup):

    def done(self):
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup-form.html', error_username = msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/upload_file')


# -----------------------------------------------------------------------------
# define a class for login page
class Login(BaseHandler):

    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/upload_file')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error = msg)


# -----------------------------------------------------------------------------
# define a class for logout page
class Logout(BaseHandler):

    def get(self):
        self.logout()
        self.redirect('/')

 
# -----------------------------------------------------------------------------
# define a class handles file upload form
class FetchHandler(BaseHandler):
    def get(self):
        # create an upload URL for the form that the user will fill out
        if not self.user:
            self.redirect('/login')
        upload_url = blobstore.create_upload_url('/parse_file')
        self.render('upload-file.html', upload_url=upload_url)
        
 
# -----------------------------------------------------------------------------
# define a class for file upload handler
class ParseHandler(BaseHandler, blobstore_handlers.BlobstoreUploadHandler):
    def post(self):
        upload = self.get_uploads('file')[0]
        blob_key = upload.key()
        blob_reader = blobstore.BlobReader(blob_key) # instantiate a BlobReader for a given BlobStore value.
        locations = parse_file(blob_reader) 
        img_url = generate_url(locations=locations) 
        if img_url != None:                
            self.render('view-map.html', img_url=img_url)
        

class Home(BaseHandler):
    def get(self):
        self.write('Welcome to TrackMaps!')

# -----------------------------------------------------------------------------
# define routings
app = webapp2.WSGIApplication([('/', Home),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ('/upload_file', FetchHandler),
                               ('/parse_file', ParseHandler),
                               ],
                              debug=True)


