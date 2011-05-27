#!/usr/bin/env python

import urllib

from oauth2 import Client, Request, Consumer, Token

import errors

from utils import parse_www_authenticate


class ApiClient(object):
    """
    OAuth client for the Mobile Vikings API.

    Overview
    --------

    OAuth is an authorization protocol that allows applications (a balance
    checker on your Android phone, for example) to consume user data from a
    service provider (the Mobile Vikings API) data without having to know the
    user's credentials.

    Registering your application
    ----------------------------

    Before you can call the Mobile Vikings API you should register your
    application. Send a request to `info@mobilevikings.com`. Don't forget to
    include the name of your application and a short description of its
    functionality. We will send you the consumer key and secret you need to
    initialize the API client.

    Acquiring an access token
    -------------------------

    The OAuth protocol implements authorization by exchanging tokens. First,
    the application fetches a request token with a given callback url. Using
    this token, it can redirect the user to an authorization url on the Mobile
    Vikings site. On this page, the user is asked if she wants to grant
    permission to the application. If she does, she is redirected to the
    callback url that now contains a verification code. The application can
    then use the verification code to request an access token. With this access
    token, the API calls can finally be made.

    Example
    -------

    >>> api = ApiClient(consumer_key, consumer_secret)
    >>> api.fetch_request_token(callback='http://my-app.com/access_granted')
    >>> url = api.make_authorization_url()

    Now, redirect the user to the authorization url. If she accepts, she
    will be redirected to the `access_granted` page of your site. There
    will be `oauth_verifier` and `oauth_token` GET query parameters present
    in the URL. Pass them to the client and fetch the access token.

    >>> request_key = request.GET['oauth_token']
    >>> request_secret = '' # Fetch this from your session or db.
    >>> verifier = request.GET['oauth_verifier']
    >>> request_token = Token(request_key, request_secret)
    >>> request_token.set_verifier(verifier)
    >>> api = ApiClient(consumer_key, consumer_secret)
    >>> api.set_request_token(request_token)
    >>> access_token = api.fetch_access_token()

    You can now use the `api` object to make calls.

    >>> api.get('top_up_history')

    Note: if you don't want to use a redirect to your application's site, omit
    the `callback` argument in the `fetch_request_token` call. The Mobile
    Vikings API will then display the verification code to the user when access
    has been granted.

    Re-using an existing access token
    ---------------------------------

    Your application can re-use the access token once it has been acquired; you
    need not go through the authorization process again. The token will stay
    valid until the user explicitly revokes it.

    >>> api = ApiClient(consumer_key, consumer_secret)
    >>> api.set_access_token(access_token)
    >>> api.get('sim_balance')
    """
    PROTOCOL = 'https'
    HOST = 'mobilevikings.com'
    PORT = 443
    VERSION = '2.0'
    FORMAT = 'json'

    PATH = '/api/' + VERSION + '/oauth/'
    BASE_URL = PROTOCOL + '://' + HOST + ':%d' % PORT + PATH
    REQUEST_TOKEN_URL = BASE_URL + 'request_token/'
    AUTHORIZE_TOKEN_URL = BASE_URL + 'authorize/'
    ACCESS_TOKEN_URL = BASE_URL + 'access_token/'

    def __init__(self, consumer_key, consumer_secret, format=FORMAT):
        """
        Construct a new API client instance.

        ``consumer_key``: key of the application consuming data from the API.
        ``consumer_secret``: secret corresponding to the consumer key.
        ``format``: output format of the API. Should be one of the following
            strings: 'json', 'xml', 'yaml', 'pickle'.

        If you don't have a consumer key and secret yet and want to develop an
        application that uses the Mobile Vikings API, send a request to
        info@mobilevikings.com. Don't forget to include the name of your
        application and a short description of its functionality.
        """
        self.consumer = Consumer(consumer_key, consumer_secret)
        self.client = Client(self.consumer)
        self.request_token = None
        self.access_token = None
        self.format = format

    @staticmethod
    def _detect_errors(response, content):
        """ Examine response and raise appropriate exception if necessary. """
        lower = content.lower()

        if response['status'] == '400' and 'invalid consumer' in lower:
            raise errors.InvalidConsumer(response, content)
        if response['status'] == '400' and 'invalid request token' in lower:
            raise errors.RequestTokenExpired(response, content)
        if response['status'] == '400' and 'could not verify' in lower:
            raise errors.AccessDenied(response, content)
        if response['status'] == '400' and 'invalid oauth verifier' in lower:
            raise errors.InvalidVerifier(response, content)
        if response['status'] == '401' and 'www-authenticate' in response:
            www_auth = response['www-authenticate']
            mech, params = parse_www_authenticate(www_auth)
            if mech == 'OAuth' and params.get('realm') == '"Mobile Vikings"':
                raise errors.AccessTokenExpired(response, content)

    def _request(self, *args, **kwargs):
        """ Perform an OAuth client request with error detection. """
        response, content = self.client.request(*args, **kwargs)
        ApiClient._detect_errors(response, content)
        return response, content

    def fetch_request_token(self, callback='oob'):
        """
        Fetch a request token.

        ``callback`` (optional): URL the user will be redirected to
        when she has granted access. Pass 'oob' to if you want the Mobile
        Vikings site to show the verification code without a redirect.

        Returns a :class:`oauth2.Token` instance.
        """
        args = {'oauth_callback': callback}
        url = self.REQUEST_TOKEN_URL + '?' + urllib.urlencode(args)
        response, content = self._request(url)
        try:
            token = Token.from_string(content)
        except ValueError:
            raise errors.ApiServerError(response, content)
        else:
            self.set_request_token(token)
            return token

    def set_request_token(self, token):
        """ Make the client use the given request token for its calls. """
        self.request_token = token
        self.client = Client(self.consumer, self.request_token)

    def make_authorization_url(self):
        """
        Generate the authorization URL on the Mobile Vikings site.

        You can redirect your user to this page to allow her to grant your
        application access to her data.

        Returns a `str`.
        """
        request = Request.from_consumer_and_token(
            consumer=self.consumer,
            token=self.request_token,
            http_url=self.AUTHORIZE_TOKEN_URL,
        )
        return request.to_url()

    def set_request_verifier(self, verifier):
        """ Set the verifier on the currently active request token. """
        self.request_token.set_verifier(verifier)
        self.client = Client(self.consumer, self.request_token)

    def fetch_access_token(self):
        """
        Fetch an access token.

        Note that you should have already fetched and verified a request token
        before calling this method.

        Returns a :class:`oauth2.Token` instance.
        """
        response, content = self._request(self.ACCESS_TOKEN_URL)
        try:
            token = Token.from_string(content)
        except ValueError:
            raise errors.ApiServerError(response, content)
        else:
            self.set_access_token(token)
            return token

    def set_access_token(self, token):
        """ Make the client use a the given access token for its calls. """
        self.access_token = token
        self.client = Client(self.consumer, self.access_token)

    def call(self, method, path, args=None, body='', headers=None,
             format=None):
        """
        Call the Mobile Vikings API.

        ``method``:  the HTTP method, 'GET' for example.
        ``path``: API method to call. See http://mobilevikings.com/api/2.0/doc/
            for an overview.
        ``args`` (optional): dictionary with parameters that will be used for
            the call.
        ``body`` (optional): body of the request.
        ``headers`` (optional): dictionary with HTTP headers.
        ``format`` (optional): output format of the API.

        Note that this method will only succeed if you have successfully
        request an access token.

        Returns a (`response`, `content`) tuple.
        """
        if args is None:
            args = {}
        if format is None:
            format = self.format
        url = self.BASE_URL + path + '.' + format
        if args:
            url += '?' + urllib.urlencode(args)
        return self._request(url, method, body, headers)

    def get(self, path, args=None, body='', headers=None, format=None):
        """ Shortcut for `call()` with 'GET' method. """
        return self.call('GET', path, args, body, headers, format)

    def post(self, path, args=None, body='', headers=None, format=None):
        """ Shortcut for `call()` with 'POST' method. """
        return self.call('POST', path, args, body, headers, format)