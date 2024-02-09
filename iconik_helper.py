import os

from iconik_api_client import IconikApiClient


class IconikHelper(IconikApiClient):

    def add_file_to_asset(self, asset_id, path_on_storage, storage_id, file_type, file_size=0, component_ids=None,
                          format_name='ORIGINAL', format_metadata=None):
        file_name = path_on_storage.split("/")[-1]
        base_dir = "/".join(path_on_storage.split("/")[:-1])

        # Get Storage Methods
        storage_methods = ["S3"]

        if format_metadata is None:
            format_metadata = []

        # Create Format
        # {"user_id":"ef7f3db6-61d7-11e9-8cfd-0a580a3c10c4","name":"SUBTITLES","metadata":[{"subtitle_language":"en","subtitle_closed_captions":"true"}],"storage_methods":["S3"]}
        create_format_args = {
            "asset_id": asset_id,
            "name": format_name,
            "metadata": format_metadata,
            "storage_methods": storage_methods
        }
        create_format_response = self.create_format(**create_format_args)
        format_id = create_format_response['id']

        # Create File Set
        # {"format_id":"cc5c0d14-c6d6-11ee-96fb-12668fe02189","storage_id":"3e5126d0-9c82-11ea-b023-0a580a3d1f3c","base_dir":"revolt/hotfolder/Standalone","name":"UPDATE_ACME_TEST_10-transcription.srt","component_ids":[]}
        create_file_set_args = {
            "format_id": format_id,
            "storage_id": storage_id,
            "base_dir": base_dir,
            "name": file_name,
            "component_ids": []
        }
        create_file_set_response = self.create_file_set(asset_id, **create_file_set_args)
        file_set_id = create_file_set_response['id']

        # Create File
        create_file_args = {
            "original_name": file_name,
            "directory_path": base_dir,
            "size": file_size,
            "file_type": "FILE",
            "storage_id": storage_id,
            "file_set_id": file_set_id,
            "format_id": format_id
        }
        create_file_response = self.create_file(asset_id, **create_file_args)
        file_id = create_file_response['id']

        return {"file_id": file_id, "format_id": format_id, "file_set_id": file_set_id}

    def add_subtitle_file_to_asset(self, asset_id, path_on_storage, storage_id, language, is_closed_captions=False):
        is_closed_captions_bool_as_str = str(is_closed_captions).lower()
        add_file_to_asset_response = self.add_file_to_asset(asset_id, path_on_storage, storage_id, "FILE", 0,
                                                            format_name="SUBTITLES",
                                                            format_metadata=[{"subtitle_language": language,
                                                                              "subtitle_closed_captions":
                                                                                  is_closed_captions_bool_as_str}])

        file_id = add_file_to_asset_response['file_id']
        format_id = add_file_to_asset_response['format_id']
        file_set_id = add_file_to_asset_response['file_set_id']
        # Create Subtitle Transcode Job
        # {}
        # create_subtitle_transcode_job_response = self.create_subtitle_transcode_job(asset_id, file_id)

        return {"file_id": file_id, "format_id": format_id, "file_set_id": file_set_id}

    @classmethod
    def derive_data_from_file(cls, file, file_storages):
        file_storage = next((storage for storage in file_storages if storage['id'] == file['storage_id']), {})
        file_storage_settings = file_storage.get('settings', {})
        file_storage_path = file_storage_settings.get('path', '')

        asset_file_directory_path = file.get('directory_path', '')
        asset_file_name = file.get('name', '')
        asset_file_path_on_storage = os.path.join(asset_file_directory_path, asset_file_name)
        asset_file_path = os.path.join(file_storage_path, asset_file_path_on_storage)

        asset_file_name_ext = None
        asset_base_file_name = None
        if asset_file_name:
            asset_file_name_split = os.path.splitext(asset_file_name)
            asset_file_name_ext = asset_file_name_split[1]
            asset_base_file_name = asset_file_name_split[0]

        return {
            'asset_file_path': asset_file_path,
            'asset_file_name_ext': asset_file_name_ext,
            'asset_base_file_name': asset_base_file_name,
            'asset_file_name': asset_file_name,
            'asset_file_path_on_storage': asset_file_path_on_storage,
            'asset_file_directory_path': asset_file_directory_path
        }

    def get_asset_file_url(self, asset_id, file_id):
        get_multipart_upload_presigned_url_response = self.get_multipart_upload_presigned_url(asset_id, file_id)
        return get_multipart_upload_presigned_url_response['url']
