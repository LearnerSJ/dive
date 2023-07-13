import chromadb
from chromadb.config import Settings
from dive.vector_db import query_utils

db_directory = "db"
vector_collection_name = "peristed_collection"


def index_documents(documents, account_id, connector_id, obj_type, llm_model):
    if len(documents) == 0:
        return
    persist_directory = db_directory
    client = chromadb.Client(
        Settings(
            persist_directory=persist_directory,
            chroma_db_impl="duckdb+parquet",
        )
    )

    collection = client.get_or_create_collection(name=vector_collection_name)

    _documents = []
    _document_ids = []
    _metadatas = []
    for document in documents:
        _documents.append(document['text'])
        _document_ids.append(document['id'])
        _metadata = {'account_id': account_id, 'connector_id': connector_id, 'obj_type': obj_type}
        if 'metadata' in document:
            _metadata.update(document['metadata'])

        _metadatas.append(_metadata)

    collection.upsert(
        documents=_documents,
        # we handle tokenization, embedding, and indexing automatically. You can skip that and add your own embeddings as well
        metadatas=_metadatas,  # filter on these!
        ids=_document_ids,  # unique for each doc
    )

    client.persist()


def delete_documents_by_connection(connector_id):
    persist_directory = db_directory
    collection_name = vector_collection_name
    client = chromadb.Client(
        Settings(
            persist_directory=persist_directory,
            chroma_db_impl="duckdb+parquet",
        )
    )
    try:
        collection = client.get_collection(collection_name)
    except ValueError:
        return
    collection.delete(where={"connector_id": connector_id})


def query_documents(query, account_id, connector_id, llm_model):
    client = chromadb.Client(
        Settings(
            persist_directory=db_directory,
            chroma_db_impl="duckdb+parquet",
        )
    )
    # Load the collection
    try:
        collection = client.get_collection(vector_collection_name)
    except ValueError:
        error_data = {'error': {}}
        error_data['error']['id'] = 'Resources Gone'
        error_data['error']['message'] = 'Requested vector collection does not exist'
        error_data['error']['status_code'] = 410
        return error_data

    docs_filter = {}
    if connector_id:
        docs_filter['connector_id'] = connector_id
    elif account_id:
        docs_filter['account_id'] = account_id

    try:
        results = collection.query(
                query_texts=query,
                where=docs_filter,
                n_results=2,
                # where={"metadata_field": "is_equal_to_this"}, # optional filter
                # where_document={"$contains":"search_string"}  # optional filter
            )

        document_list = []
        item_list = []

        for result in results['ids']:
            for i, id in enumerate(result):
                if len(item_list) < i + 1:
                    item_list.append({})
                item_list[i]['id'] = id

        for result in results['documents']:
            for i, sentence in enumerate(result):
                if len(item_list) < i + 1:
                    item_list.append({})
                item_list[i]['document'] = sentence
                document_list.append(sentence)

        for result in results['metadatas']:
            for i, metadata in enumerate(result):
                if len(item_list) < i + 1:
                    item_list.append({})
                item_list[i]['metadata'] = metadata

        for result in results['distances']:
            for i, distance in enumerate(result):
                if len(item_list) < i + 1:
                    item_list.append({})
                item_list[i]['distance'] = distance

        summary_list = query_utils.get_text_summarization(document_list, llm_model)

        return {'documents':item_list,'summary':summary_list}
    except Exception as e:
        error_data = {'error': {}}
        error_data['error']['id'] = 'Bad request'
        error_data['error']['status_code'] = 400
        error_data['error']['message'] = str(e)  # 'Index data is missing, please sync data source'
        return error_data

    
    return None