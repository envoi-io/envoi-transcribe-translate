import http.client
import json
import logging
import urllib.parse

logger = logging.getLogger(__name__)


class IconikHttpClient:
    DEFAULT_BASE_URL = "https://apo.iconik.io/API"

    def __init__(self, app_id, auth_token, base_url=DEFAULT_BASE_URL):
        self.conn = None
        self.base_url = base_url

        parsed_url = urllib.parse.urlparse(base_url)
        self.host = parsed_url.hostname
        self.host_port = parsed_url.port
        self.base_path = parsed_url.path

        self.init_connection()

        self.default_headers = {"Content-Type": "application/json"}
        self.default_query = {}
        self.set_auth(app_id, auth_token)

    def init_connection(self):
        self.conn = http.client.HTTPSConnection(self.host, self.host_port)

    def set_auth(self, app_id, auth_token):
        self.default_headers['App-ID'] = app_id
        self.default_headers['Auth-Token'] = auth_token

    # Token setter
    def set_auth_token(self, token):
        self.default_query['Auth-Token'] = token

    def build_headers(self, headers=None, default_headers=None):
        if headers is None:
            _headers = default_headers or self.default_headers
        else:
            if default_headers is None:
                default_headers = self.default_headers or {}
            _headers = {**default_headers, **headers}
        return _headers

    def build_query_string(self, query=None, default_query=None):
        if query is None:
            _query = default_query or self.default_query
        else:
            if default_query is None:
                default_query = self.default_query or {}
            _query = {**default_query, **query}
        return urllib.parse.urlencode(_query)

    @classmethod
    def handle_response(cls, response):
        response_body = response.read()
        content_type, header_attribs_raw = response.getheader("Content-Type").split(";")
        header_attribs = dict(map(lambda x: x.strip().split("="), header_attribs_raw.split(",")))
        charset = header_attribs.get("charset", "utf-8")
        try:
            if content_type == 'text/plain:':
                return response_body.decode(charset)
            if content_type == "application/json":
                response_as_string = response_body.decode(charset)
                return json.loads(response_as_string) if response_as_string.strip() else None
            else:
                return response_body
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding response: {e}")
            return response_body

    def build_url(self, base_path, endpoint, query=None):
        url = base_path + "/" + endpoint
        url += "?" + self.build_query_string(query=query)
        return url

    def get(self, endpoint, query=None, headers=None, default_headers=None):
        url = self.build_url(self.base_path, endpoint, query=query)
        self.conn.request("GET", url, headers=self.build_headers(headers=headers, default_headers=default_headers))
        response = self.conn.getresponse()
        return self.__class__.handle_response(response)

    def post(self, endpoint, data, query=None, headers=None, default_headers=None):
        url = self.build_url(self.base_path, endpoint, query=query)
        self.conn.request("POST", url, body=json.dumps(data),
                          headers=self.build_headers(headers=headers, default_headers=default_headers))
        response = self.conn.getresponse()
        return self.__class__.handle_response(response)


class IconikApiClient(IconikHttpClient):
    def __init__(self, app_id, auth_token, base_url=IconikHttpClient.DEFAULT_BASE_URL):
        super().__init__(app_id, auth_token, base_url)

    def create_format(self, asset_id, user_id, name, metadata, storage_methods):
        endpoint = f"/files/v1/assets/{asset_id}/formats/"
        data = {
            "user_id": user_id,
            "name": name,
            "metadata": metadata,
            "storage_methods": storage_methods
        }
        return self.post(endpoint, data)

    def create_file_set(self, asset_id, format_id, storage_id, base_dir, name, component_ids):
        endpoint = f"/files/v1/assets/{asset_id}/file_sets/"
        data = {
            "format_id": format_id,
            "storage_id": storage_id,
            "base_dir": base_dir,
            "name": name,
            "component_ids": component_ids
        }
        return self.post(endpoint, data)

    def create_file(self, asset_id, original_name, directory_path, size, file_type, storage_id, file_set_id, format_id):
        endpoint = f"/files/v1/assets/{asset_id}/files/"
        data = {
            "original_name": original_name,
            "directory_path": directory_path,
            "size": size,
            "type": file_type,
            "storage_id": storage_id,
            "file_set_id": file_set_id,
            "format_id": format_id
        }
        return self.post(endpoint, data)

    def create_subtitle_transcode_job(self, asset_id, file_id):
        endpoint = f"/files/v1/assets/{asset_id}/files/{file_id}/subtitles/"
        return self.post(endpoint, {})

    def get_asset_files(self, asset_id):
        endpoint = f"/files/v1/assets/{asset_id}/files/"
        return self.get(endpoint)

    def get_asset_format(self, asset_id, format_id):
        endpoint = f"/files/v1/assets/{asset_id}/formats/{format_id}/"
        return self.get(endpoint)

    def get_asset_formats(self, asset_id):
        endpoint = f"/files/v1/assets/{asset_id}/formats/"
        return self.get(endpoint)

    def get_asset_file_sets(self, asset_id):
        endpoint = f"/files/v1/assets/{asset_id}/file_sets/"
        return self.get(endpoint)

    def get_asset_proxies(self, asset_id, per_page, last_id, content_disposition, generate_signed_url = False):
        endpoint = f"/files/v1/assets/{asset_id}/proxies/"
        query = {
            "per_page": per_page,
            "last_id": last_id,
            "content_disposition": content_disposition,
            "generate_signed_url": generate_signed_url
        }
        return self.get(endpoint, query=query)

    def get_multipart_upload_presigned_url(self, asset_id, file_id):
        endpoint = f"/files/v1/assets/{asset_id}/files/{file_id}/multipart_url/"
        return self.get(endpoint)

    def get_multipart_part_upload_presigned_url(self, asset_id, file_id, upload_id, part_number):
        endpoint = f"/files/v1/assets/{asset_id}/files/{file_id}/multipart_url/part/"
        query = {
            "upload_id": upload_id,
            "parts_num": part_number
        }
        return self.get(endpoint, query=query)

    def get_storage(self, storage_id):
        endpoint = f"/files/v1/storages/{storage_id}/"
        return self.get(endpoint)

    def get_storages(self):
        endpoint = f"/files/v1/storages/"
        return self.get(endpoint)
