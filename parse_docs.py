import requests
import os
import argparse

input_dir = 'data/test_pdfs'
output_dir = 'data'
batch_id_file = 'data/batch_id.txt'
batch_size = 10

token = os.getenv('MINERU_TOKEN')
upload_url = 'https://mineru.net/api/v4/file-urls/batch'

header = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {token}"
}

# upload_files = [os.path.join(input_dir, f) for f in os.listdir(input_dir)]
# 
# batch_ids = []
# for i in range(0, len(upload_files), batch_size):
#     batch_files = upload_files[i:i+batch_size]
#     batch_data = {
#         'model_version': 'vlm',
#         'language': 'ch',
#         'files': [
#             {
#                 'name': os.path.basename(f),
#                 'data_id': os.path.splitext(os.path.basename(f))[0]
#             } for f in batch_files
#         ]
#     }
#     try:
#         response = requests.post(upload_url, headers=header, json=batch_data)
#         if response.status_code == 200:
#             result = response.json()
#             print(f'Response success: {result}')
#             if result['code'] == 0:
#                 batch_ids.append(result['data']['batch_id'])
#                 for url, path in zip(result['data']['file_urls'], batch_files):
#                     with open(path, 'rb') as f:
#                         res_upload = requests.put(url, data=f)
#                         if res_upload.status_code == 200:
#                             print(f"{url} upload success")
#                         else:
#                             print(f"{url} upload failed")
#             else:
#                 print(f'Apply upload url failed: {result["msg"]}')
#         else:
#             print(f'Response failed: {response}')
#     except Exception as err:
#         print(err)
# 
# if batch_ids:
#     with open(batch_id_file, 'w') as f:
#         for bid in batch_ids:
#             f.write(f'{bid}\n')
# else:
#     print('No batch uploaded')



with open(batch_id_file, 'r') as f:
    for batch_id in f:
        url = f"https://mineru.net/api/v4/extract-results/batch/{batch_id}"
        res = requests.get(url, headers=header)
        print(res.status_code)
        print(res.json())


