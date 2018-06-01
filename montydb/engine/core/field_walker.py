
from collections import deque, OrderedDict

from ..helpers import (
    is_array_type,
    is_mapping_type,
)


def is_array_type_(doc):
    return is_array_type(doc) or isinstance(doc, _FieldValues)


class FieldWalker(object):
    """Document traversal context manager
    """

    __slots__ = [
        "doc",
        "matched_indexes",

        "_value",
        "_exists",
        "_embedded_in_array",
        "_index_posed",
        "_been_in_array",

        # FLAGS_FOR_NONE_QUERYING
        "_NQF_docs_field_missing_in_array",
        "_NQF_array_field_not_exists_in_all_elements",
        "_NQF_out_of_array_index",
        "_NQF_no_docs_in_array",

        "_elem_iter_map",
        "_query_path",
    ]

    def __init__(self, doc):
        """
        Args:
            doc (dict): Document object
        """
        self.doc = doc
        self.matched_indexes = {}
        self.reset()

    def __call__(self, path):
        """Walk through document and acquire value with given key-path

        Args:
            path (string): Document field path
        """
        doc_ = self.doc
        self.reset()

        self._query_path = path
        for field in path.split("."):

            array_index_pos = False
            array_has_doc = False
            if is_array_type_(doc_):
                if len(doc_) == 0:
                    self._exists = False
                    break

                self._been_in_array = True
                array_has_doc = any(is_mapping_type(e_) for e_ in doc_)
                array_index_pos = field.isdigit()

                if array_index_pos:
                    if self._index_posed and self._embedded_in_array:
                        array_index_pos = any(is_array_type(e_) for e_ in doc_)
                else:
                    doc_ = self._walk_array(doc_, field)

            # Is the path ends with index position ?
            self._index_posed = array_index_pos

            # If the `doc_` is an array (or `_FieldValues` type) and containing
            # documents, those documents possible has numeric string key,
            # for example: [{"1": <value>}, ...]
            if array_index_pos and array_has_doc:
                # Index position path As a Field of `doc_`
                iaf_doc_ = self._walk_array(doc_, field)
                # Append index position result to the document field result
                if iaf_doc_ is not None:
                    if len(doc_) > int(field):  # Make sure index in range
                        if isinstance(doc_, _FieldValues):
                            iaf_doc_[field] += doc_.positional(int(field))
                        else:
                            iaf_doc_[field].append(doc_[int(field)])

                    doc_ = iaf_doc_
                    array_index_pos = False

            if array_index_pos and self._embedded_in_array:
                # the `doc_` in here must be `_FieldValues` type
                doc_ = {field: doc_.positional(int(field))}
                array_index_pos = False

            try:
                # Try getting value with key(field) or index.
                doc_ = doc_[int(field) if array_index_pos else field]
                self._exists = True

            except (KeyError, IndexError, TypeError) as err:
                ecls = err.__class__
                # Raising some flags if conditions match.

                # FLAGS_FOR_NONE_QUERYING:
                #   possible index position out of length of array
                self._NQF_out_of_array_index = ecls is IndexError
                # FLAGS_FOR_NONE_QUERYING:
                #   possible not field missing, but the array has no document
                if ecls is TypeError and self._been_in_array:
                    self._NQF_no_docs_in_array = (
                        not self._NQF_docs_field_missing_in_array)

                # Reset partialy and stop field walking.
                doc_ = None
                self.reset(partial=True)
                break

        """End of walk"""

        # Collecting values
        if not array_index_pos and is_array_type_(doc_):
            # Extend `fieldValues.elements` with an array field value from
            # a single document or from multiple documents inside an array.
            self._value.extend(doc_)
        # Append to `fieldValues.arrays`, but if `doc_` is not array type,
        # will be append to `fieldValues.elements`.
        self._value.append(doc_)

        # FLAGS_FOR_NONE_QUERYING:
        #   Correcting flag after value been collected.
        #       Confirm all documents inside the array have no such field,
        #       instead of missing field in some of the documents.
        if (None not in self._value.elements and
                not self._NQF_array_field_not_exists_in_all_elements):
            self._NQF_docs_field_missing_in_array = False

        return self

    def _walk_array(self, doc_, field):
        """Walk in to array for embedded documents.
        """
        field_values = _FieldValues()
        num_of_emb_doc = 0
        self._elem_iter_map[field] = OrderedDict()

        for i, emb_doc in enumerate(doc_):
            if not is_mapping_type(emb_doc):
                continue
            num_of_emb_doc += 1

            emb_field = FieldWalker(emb_doc)(field)
            if emb_field.exists:
                self._elem_iter_map[field][i] = len(emb_field.value.elements)
                field_values += emb_field.value
            else:
                # FLAGS_FOR_NONE_QUERYING:
                #   field not exists in all elements.
                self._NQF_array_field_not_exists_in_all_elements = True

        if len(field_values.arrays) != num_of_emb_doc:
            # FLAGS_FOR_NONE_QUERYING:
            #   Possible missing field in some documents.
            #       Using `field_values.arrays` length to compare is not
            #       accurate, but will correcting the result after all value
            #       been collected.
            self._NQF_docs_field_missing_in_array = True

        if field_values:
            self._embedded_in_array = True
            return {field: field_values}
        else:
            return None

    def reset(self, partial=None):
        """Rest all, or keeping some flags for internal use.
        """
        self._value = _FieldValues()
        self._exists = False
        self._embedded_in_array = False
        self._index_posed = False
        self._elem_iter_map = OrderedDict()
        self._query_path = ""

        if not partial:
            self._been_in_array = False
            self._NQF_docs_field_missing_in_array = False
            self._NQF_array_field_not_exists_in_all_elements = False
            self._NQF_out_of_array_index = False
            self._NQF_no_docs_in_array = False

    def _get_matched_index(self):
        times = self._value.iter_times
        if len(self._elem_iter_map) == 0:
            return None if len(self._value.elements) == 0 else (times - 1)
        else:
            while len(self._elem_iter_map):
                for ind, len_ in self._elem_iter_map.popitem()[1].items():
                    if times > len_:
                        times -= len_
                    else:
                        times = ind + 1
                        break
            return times - 1

    def __enter__(self):
        return self

    def __exit__(self, *args):
        root = self._query_path.split(".", 1)[0]
        self.matched_indexes[root] = self._get_matched_index()
        self.reset(partial=True)

    @property
    def value(self):
        """An instance of `_FieldValues`, hold the result of the query."""
        return self._value

    @property
    def exists(self):
        """Is the path of this query exists ?"""
        return self._exists

    @property
    def embedded_in_array(self):
        """Is the results from documents embedded in array ?"""
        return self._embedded_in_array

    @property
    def index_posed(self):
        """Is the path of this query ends with index position ?"""
        return self._index_posed

    @property
    def array_field_missing(self):
        """Documents in array has missing field

        Possible some of document embedded in array has field missing,
        or all document in array has no such field existed.
        """
        return self._NQF_docs_field_missing_in_array

    @property
    def array_status_normal(self):
        """No missing field but the path not exists

        Query path not existed in document array due to array out of index
        or has no document object in array.
        In this case, the field was not missing because it's possible that
        field did not meant to be there (because no embedded document) or
        array out of index if the path is index position, and since the field
        was not missing, the document won't pop when querying `None`.
        """
        return self._NQF_out_of_array_index or self._NQF_no_docs_in_array

    def matched_index(self, path):
        return self.matched_indexes.get(path.split(".", 1)[0])


class _FieldValues(object):

    __slots__ = [
        "elements",
        "arrays",
        "iter_queue",
        "iter_times",
    ]

    def __init__(self, elements=None, arrays=None):
        self.elements = elements or []
        self.arrays = arrays or []
        self.iter_queue = deque()
        self.iter_times = 1

    def _merged(self):
        return self.elements + self.arrays

    def __repr__(self):
        return str(self._merged())

    def __next__(self):
        if len(self.iter_queue):
            self.iter_times += 1
            return self.iter_queue.popleft()
        else:
            raise StopIteration

    next = __next__

    def __iter__(self):
        self.iter_times = 0
        self.iter_queue = deque(self._merged())
        return self

    def __len__(self):
        return len(self._merged())

    def __eq__(self, other):
        return self._merged() == other

    def __bool__(self):
        return bool(self.elements or self.arrays)

    __nonzero__ = __bool__

    def __getitem__(self, index):
        return self.elements[index]

    def __iadd__(self, val):
        self.elements += val.elements
        self.arrays += val.arrays
        return self

    def extend(self, val):
        if isinstance(val, _FieldValues):
            self.elements += val.elements
        else:
            self.elements += val

    def append(self, val):
        if isinstance(val, _FieldValues):
            self.arrays += val.arrays
        else:
            if is_array_type(val):
                self.arrays.append(val)
            else:
                self.elements.append(val)

    def positional(self, index):
        self.elements = [val[index] for val in self.arrays
                         if len(val) > index]
        self.arrays = []

        return self
