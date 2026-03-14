import os
import oss2
from dotenv import load_dotenv

load_dotenv()

def get_bucket():
    key_id     = os.getenv("OSS_ACCESS_KEY_ID")
    key_secret = os.getenv("OSS_ACCESS_KEY_SECRET")
    endpoint   = os.getenv("OSS_ENDPOINT")
    bucket_name = os.getenv("OSS_BUCKET_NAME")
    
    print(f"key_id: {key_id}")
    print(f"key_secret: {key_secret}")
    print(f"endpoint: {endpoint}")
    print(f"bucket: {bucket_name}")
    
    auth   = oss2.Auth(key_id, key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    return bucket