import requests
import os
import argparse

input_dir = 'data/finance_pdfs'
output_dir = 'data'
batch_id_filename = 'data/batch_id.txt'
batch_size = 10

token = os.getenv('MINERU_TOKEN')
upload_url = 'https://mineru.net/api/v4/file-urls/batch'

header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

upload_files = [os.path.join(input_dir, f) for f in os.listdir(input_dir)]

upload_data = {
    "model_version": "vlm",
    "language": "ch",
    "files": [
        {
            "name": os.path.basename(f),
            "data_id": os.path.splitext(os.path.basename(f))[0]
        }
    ]
}

for i in range(0, len(upload_files), batch_size):
    batch_files = upload_files[i:i+batch_size]
    batch_data = {
        'model_version': 'vlm',
        'language': 'ch',
        'files': [
            {
                'name': os.path.basename(f),
                'data_id': os.path.splitext(os.path.basename(f))[0]
            } for f in batch_files
        ]
    }
    batch_ids = []
    try:
        response = requests.post(upload_url, headers=header, json=batch_data)
        if response.status_code == 200:
            result = response.json()
            print(f'Response success: {result}')
            if result['code'] == 0:
                for url, path in zip(result['data']['file_urls'], batch_files):
                    with open(path, 'rb') as f:
                        res_upload = requests.put(url, data=f)
                        if res_upload.status_code == 200:
                            print(f"{urls[i]} upload success")
                            batch_ids.append(result['data']['batch_id'])
                        else:
                            print(f"{urls[i]} upload failed")
            else:
                print(f'Apply upload url failed: {result["msg"]}')
        else:
            print(f'Response failed: {response}')
    except Exception as err:
        print(err)


# batch_id = 'd979fcb6-2a43-4a48-b647-65ee84098394'
# url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
# header = {
#     "Content-Type": "application/json",
#     "Authorization": f"Bearer {token}"
# }
# 
# res = requests.get(url, headers=header)
# print(res.status_code)
# print(res.json())
# print(res.json()["data"])


