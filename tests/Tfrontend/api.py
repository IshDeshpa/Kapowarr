import os
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from backend.base.custom_exceptions import FileNotFound
from frontend.api import api


class FileDownloadEndpointTests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(api, url_prefix='/api')
        self.client = self.app.test_client()

    def test_downloads_file_as_attachment(self):
        with tempfile.NamedTemporaryFile(
            suffix='.cbz', delete=False
        ) as file:
            file.write(b'comic data')
            filepath = file.name

        self.addCleanup(os.remove, filepath)

        with patch('frontend.api.extract_key'):
            with patch(
                'frontend.api.FilesDB.fetch',
                return_value=[{'id': 1, 'filepath': filepath, 'size': 10}]
            ):
                response = self.client.get('/api/files/1/download')

        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b'comic data')
        self.assertIn('attachment', response.headers['Content-Disposition'])
        self.assertIn(
            os.path.basename(filepath),
            response.headers['Content-Disposition']
        )
        self.assertEqual(response.headers['Content-Length'], '10')
        self.assertEqual(
            response.headers['Content-Type'],
            'application/vnd.comicbook+zip'
        )
        self.assertEqual(response.headers['Cache-Control'], 'no-cache')
        self.assertEqual(response.headers['Accept-Ranges'], 'bytes')

    def test_supports_range_requests(self):
        with tempfile.NamedTemporaryFile(
            suffix='.cbz', delete=False
        ) as file:
            file.write(b'comic data')
            filepath = file.name

        self.addCleanup(os.remove, filepath)

        with patch('frontend.api.extract_key'):
            with patch(
                'frontend.api.FilesDB.fetch',
                return_value=[{'id': 1, 'filepath': filepath, 'size': 10}]
            ):
                response = self.client.get(
                    '/api/files/1/download',
                    headers={'Range': 'bytes=0-4'}
                )

        self.addCleanup(response.close)
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.data, b'comic')
        self.assertEqual(response.headers['Content-Range'], 'bytes 0-4/10')

    def test_preserves_unicode_filename(self):
        with tempfile.TemporaryDirectory() as folder:
            filepath = os.path.join(folder, 'Mañana #1.cbz')
            with open(filepath, 'wb') as file:
                file.write(b'comic data')

            with patch('frontend.api.extract_key'):
                with patch(
                    'frontend.api.FilesDB.fetch',
                    return_value=[{
                        'id': 1,
                        'filepath': filepath,
                        'size': 10
                    }]
                ):
                    response = self.client.get('/api/files/1/download')

            disposition = response.headers['Content-Disposition']
            self.assertIn("filename*=UTF-8''", disposition)
            self.assertIn('Ma%C3%B1ana%20#1.cbz', disposition)
            response.close()

    def test_returns_not_found_for_unknown_file(self):
        with patch('frontend.api.extract_key'):
            with patch(
                'frontend.api.FilesDB.fetch',
                side_effect=FileNotFound(1)
            ):
                response = self.client.get('/api/files/1/download')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json['error'], 'FileNotFound')

    def test_returns_not_found_when_file_no_longer_exists(self):
        missing_path = '/tmp/kapowarr-missing-comic.cbz'

        with patch('frontend.api.extract_key'):
            with patch(
                'frontend.api.FilesDB.fetch',
                return_value=[{'id': 1, 'filepath': missing_path, 'size': 10}]
            ):
                response = self.client.get('/api/files/1/download')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json['error'], 'FileNotFound')
        self.assertEqual(response.json['result']['filepath'], missing_path)
