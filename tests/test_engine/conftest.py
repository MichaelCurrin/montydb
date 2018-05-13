
import pytest


def insert(db, docs):
    db.drop_collection("test")
    col = db["test"]
    for i, d in enumerate(docs):
        d['_id'] = i
    col.insert_many(docs)
    return col


def insert_and_find(db, docs, spec):
    col = insert(db, docs)
    return col.find(spec)


@pytest.fixture
def monty_find(monty_database):
    def _insert_and_find(docs, spec, db=monty_database):
        return insert_and_find(db, docs, spec)
    return _insert_and_find


@pytest.fixture
def mongo_find(mongo_database):
    def _insert_and_find(docs, spec, db=mongo_database):
        return insert_and_find(db, docs, spec)
    return _insert_and_find


def insert_and_project(db, docs, spec, proj):
    col = insert(db, docs)
    return col.find(spec, proj)


@pytest.fixture
def monty_proj(monty_database):
    def _insert_and_project(docs, spec, proj, db=monty_database):
        return insert_and_project(db, docs, spec, proj)
    return _insert_and_project


@pytest.fixture
def mongo_proj(mongo_database):
    def _insert_and_project(docs, spec, proj, db=mongo_database):
        return insert_and_project(db, docs, spec, proj)
    return _insert_and_project


def insert_and_sort(db, docs, sort):
    col = insert(db, docs)
    return col.find({}).sort(sort)


@pytest.fixture
def monty_sort(monty_database):
    def _insert_and_sort(docs, sort, db=monty_database):
        return insert_and_sort(db, docs, sort)
    return _insert_and_sort


@pytest.fixture
def mongo_sort(mongo_database):
    def _insert_and_sort(docs, sort, db=mongo_database):
        return insert_and_sort(db, docs, sort)
    return _insert_and_sort
