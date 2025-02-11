import os

import firebase_admin
from django.conf import settings
from firebase_admin import credentials
from firebase_admin import firestore

# cred = credentials.Certificate('../')
cred_path = os.path.join(settings.BASE_DIR, 'firebase-credentials.json')
print(cred_path)

cred = credentials.Certificate(cred_path)
firebase_admin.initialize_app(cred)

# Initialize Firestore DB
db = firestore.client()


def write_in_executor_firestore(document_id='codeknot_random', data=None, messages=False):
# Add data to a collection
    doc_ref = db.collection('executor').document(document_id)
    # Set the document with merge
    doc = doc_ref.get()
    if doc.exists:
        current_data = doc.to_dict()
        print(f'Current data: {current_data}')
        if messages and current_data["messages"]:
            new_messages = current_data["messages"] + data.pop('messages')
            current_data["messages"] = new_messages
            current_data.update(data)
            doc_ref.set(current_data, merge=True)
            print('Document set with merge successfully.')
            return
    doc_ref.set(data, merge=True)
    print('Document set with merge successfully.')


def read_in_executor_firestore(document_id='codeknot_random'):
    # Add data to a collection
    doc_ref = db.collection('executor').document(document_id)
    # Fetch the document
    doc = doc_ref.get()
    if doc.exists:
        current_data = doc.to_dict()
        print(f'Current data: {current_data}')
    else:
        print('No such document!')

