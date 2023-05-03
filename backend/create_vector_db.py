from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.embeddings import OpenAIEmbeddings
from langchain.vectorstores import Pinecone
import pinecone
from urllib.request import Request

import pandas as pd
import tiktoken

from tqdm import tqdm

import os
import re
import zipfile
from urllib.request import urlopen
from io import BytesIO

# Import dotenv and load the variables from .env file
from dotenv import load_dotenv
load_dotenv()

def zipfile_from_github():
    req = Request(os.environ['ZIP_URL'])
    token = os.environ['GITHUB_TOKEN'] if 'GITHUB_TOKEN' in os.environ else None
    print(token, os.environ['ZIP_URL'])
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    http_response = urlopen(req)

    # Save the zip file to filesystem
    with open('data/downloaded_zip.zip', 'wb') as f:
        f.write(http_response.read())
    
    # Return the zipfile object using the file saved on the filesystem
    return zipfile.ZipFile('data/downloaded_zip.zip', 'r')

embeddings = OpenAIEmbeddings(
    openai_api_key=os.environ['OPENAI_API_KEY'],
    openai_organization=os.environ['OPENAI_ORG_ID'],
)
encoder = tiktoken.get_encoding('cl100k_base')

pinecone.init(
    api_key=os.environ['PINECONE_API_KEY'],
    environment=os.environ['ENVIRONMENT']
)
vector_store = Pinecone(
    index=pinecone.Index(os.environ['PINECONE_INDEX']),
    embedding_function=embeddings.embed_query,
    text_key='text',
    namespace=os.environ['NAMESPACE']
)

splitter = RecursiveCharacterTextSplitter(
    chunk_size=int(os.environ['CHUNK_SIZE']),
    chunk_overlap=int(os.environ['CHUNK_OVERLAP'])
    )

total_tokens, corpus_summary = 0, []
file_texts, metadatas = [], []
with zipfile_from_github() as zip_ref:
    zip_file_list = zip_ref.namelist()
    
    pbar = tqdm(zip_file_list, desc=f'Total tokens: 0')
    for file_name in pbar:
        if (file_name.endswith('/') or 
            any(f in file_name for f in ['.DS_Store', '.gitignore']) or 
            any(file_name.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.mp3'])
        ):
            continue
        else:
            with zip_ref.open(file_name, 'r') as file:
                file_contents = str(file.read())
                file_name_trunc = re.sub(r'^[^/]+/', '', str(file_name))
                
                n_tokens = len(encoder.encode(file_contents))
                total_tokens += n_tokens
                corpus_summary.append({'file_name': file_name_trunc, 'n_tokens': n_tokens})

                file_texts.append(file_contents)
                metadatas.append({'document_id': file_name_trunc})
                pbar.set_description(f'Total tokens: {total_tokens}')

split_documents = splitter.create_documents(file_texts, metadatas=metadatas)
vector_store.from_documents(
    documents=split_documents, 
    embedding=embeddings,
    index_name=os.environ['PINECONE_INDEX'],
    namespace=os.environ['NAMESPACE']
)

pd.DataFrame.from_records(corpus_summary).to_csv('data/corpus_summary.csv', index=False)