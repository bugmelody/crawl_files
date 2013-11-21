__author__ = 'JamesBond <qinchuanemail@gmail.com>'

"""
download file
how to use callback
http://stackoverflow.com/questions/5925028/urllib2-post-progress-monitoring
http://stackoverflow.com/questions/2028517/python-urllib2-progress-hook
"""
import urllib2
import urlparse
import os
import socket
import traceback


class DenyMimes(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class CanNotGuessExtension(Exception):
    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class DownError(Exception):
    """
    represent all error when downloading
    I want to unify all exceptions in DownFile to DownError,including (httperror,urlerror,socket.timetout)
    so that the external program only need to catch DownError exception
    """

    def __init__(self, msg):
        self.msg = msg

    def __str__(self):
        return self.msg


class DownFile(object):
    def __init__(self, url, save_dir, save_file_without_ext, downing_callback=None):
        """
        :param url: file url,can be http,https,ftp
        :param save_dir: save file to where
        :param save_file_without_ext: filename without ext
        :param downing_callback: used to do something when downing,e.g. progress logging,mysql ping
        """
        self.url = url
        self.save_dir = save_dir
        self.save_file_without_ext = save_file_without_ext
        self.save_file_ext = None
        self.response = None
        self.header_file_bytes = None
        # already downloaded file size in bytes
        self.downloaded_bytes = 0
        self.content_disposition = None
        self.mime_type = None
        # because url may be redirect, so this variable is used to record download file from what real url
        self.what_url = None
        self.downing_callback = downing_callback
        self.deny_mimes = ('text/plain', 'text/html', 'application/xml',
                           'text/xml', 'text/css', 'application/javascript',
                           'text/javascript', 'application/xhtml+xml')
        self.headers_for_request = {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-cn,zh;q=0.8,en-us;q=0.5,en;q=0.3',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Referer': "http://www.google.com",
            'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64; rv:24.0) Gecko/20100101 Firefox/24.0',
        }
        self.chunk_read_size = 16384  # 16 * 1024
        self.request_time_out = 40

    def get_file_full_path(self):
        """
        return file full path
        """
        return self.save_dir + os.sep + self.save_file_without_ext + self.save_file_ext

    def ensure_dir(self):
        if not os.path.isdir(self.save_dir):
            os.makedirs(self.save_dir)

    def resolve_what_url(self):
        if self.url != self.response.url:
            self.what_url = self.response.url
        else:
            self.what_url = self.url

    def guess_ext_from_content_disposition(self):
        """
        guess ext from http header content-disposition if have
        """
        # may be bug, Content-Disposition attachment; filename="MyspacePasswordDecryptor.zip";
        if self.content_disposition:
            file_name = self.content_disposition.split('filename=')[1]
            # "MyspacePasswordDecryptor.zip"; maybe like this,so rstrip semicolon
            file_name = file_name.rstrip(';')
            # web server can pass wrong formatted name as ["file.ext] or [file.ext'] or even be empty
            file_name = file_name.replace('"', '').replace("'", "")
            if '' == file_name:
                self.save_file_ext = None
            else:
                if -1 != file_name.find('.'):
                    file_name_list = file_name.split('.')
                    self.save_file_ext = '.' + file_name_list[-1]
                else:
                    self.save_file_ext = ''

    def guess_ext_from_url(self):
        """
        this may be a problem
        Worked very well, but I would wrap urlsplit(url)[2] with a call to urllib.unquote,
        otherwise the filenames would be percent-encoded.
        Here is how I'm doing: return basename(urllib.unquote(urlsplit(url)[2]))
        """
        # http://docs.python.org/2.7/library/urlparse.html#urlparse.urlsplit
        # 0:scheme,1:netloc,2:path,3:query
        url_path = urlparse.urlsplit(self.what_url)[2]
        # path index is 2,Hierarchical path,may be empty string
        if '' == url_path:
            self.save_file_ext = None
        else:
            # 0: root 1: .ext
            file_name_info = os.path.splitext(url_path)
            # '.exe', contain .
            self.save_file_ext = file_name_info[1]

    def auto_get_file_extension(self):
        """
        auto guess file ext
        if can not guess,self.save_file_ext is None
        self.save_file_ext always contain .
        """
        self.resolve_what_url()
        self.guess_ext_from_content_disposition()
        # guess ext from content_disposition success
        if None != self.save_file_ext:
            return
        else:
            self.guess_ext_from_url()

    def do_request(self):
        self.ensure_dir()
        request = urllib2.Request(self.url, None, self.headers_for_request)
        # if url empty,will raise ValueError: unknown url type
        self.response = urllib2.urlopen(request, None, self.request_time_out)

    def down(self):
        """
        if down success,no Exception
        else, DenyMimes,CanNotGuessExtension,DownError will raise
        """
        try:
            self.do_request()
            info = self.response.info()
            self.mime_type = info.gettype()
            if self.mime_type in self.deny_mimes:
                raise DenyMimes('Wrong Mime type: ' + self.mime_type)
            self.header_file_bytes = int(info.getheader("Content-Length", '0').strip())
            self.content_disposition = info.getheader("Content-Disposition", '')

            self.auto_get_file_extension()
            if None == self.save_file_ext:
                raise CanNotGuessExtension('Can not guess file extension, the url is: ' + self.url)

            local_file_full_path = self.save_dir + os.sep + self.save_file_without_ext + self.save_file_ext
            outfile = open(local_file_full_path, 'wb')
            self.downloaded_bytes = 0
            while True:
                s = self.response.read(self.chunk_read_size)
                read_len = len(s)
                if self.downing_callback:
                    self.downing_callback(self)  # this is a hook
                if read_len == 0:
                    break
                outfile.write(s)
                self.downloaded_bytes += read_len

        except urllib2.HTTPError, e:
            raise DownError('urllib2.HTTPError code: %s' % (e.code,))
        except urllib2.URLError, e:
            raise DownError('urllib2.URLError:reason: %s' % (str(e.reason),))
        except socket.timeout, e:
            raise DownError('socket.timeout: %s' % (str(e),))
        except Exception, e:
            raise DownError('unknown exception: %s' % (str(e) + traceback.format_exc(),))
        else:
            pass
        finally:
            pass


class DownManager(object):
    def __init__(self):
        self.last_err_msg = ''

    def down(self, url, save_dir, save_file_without_ext, downing_callback, max_try):
        """
        download file,do retry,if failed after retry,raise DownError(last error)
        if success, return DownFile object
        """
        i = 1
        while i <= max_try:
            try:
                down_file = DownFile(url, save_dir, save_file_without_ext, downing_callback)
                down_file.down()
            except DenyMimes, e:
                self.last_err_msg = str(e)
                raise e  # no need to download
            except CanNotGuessExtension, e:
                self.last_err_msg = str(e)
                raise e  # no need to download
            except DownError, e:
                self.last_err_msg = str(e)
                i += 1
            else:
                return down_file
            finally:
                pass
        raise DownError(self.last_err_msg)


if __name__ == '__main__':

    manager = DownManager()
    urls = {
        'a': 'http://ramui.com/webblog/download-v1.html'
    }
    for (k, v) in urls.items():
        try:
            down_file_test = manager.down(v, './downloadtest', 'test' + k, None, 4)
        except DenyMimes, ex:
            print(str(ex))
        except CanNotGuessExtension, ex:
            print(str(ex))
        except DownError, ex:
            print('download failed,error: ' + str(ex))
        else:
            print('download success,full file path is: ' + down_file_test.get_file_full_path())
