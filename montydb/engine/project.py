
from bson.py3compat import string_type

from ..errors import OperationFailure
from .base import FieldWalker
from .queries import QueryFilter
from .helpers import (
    is_mapping_type,
    is_array_type,
)


def _is_include(val):
    """
    [] and "" will be `True` as well
    """
    return bool(is_array_type(val) or isinstance(val, string_type) or val)


def _is_positional_match(conditions, match_field):
    """
    @conditions `.queries.LogicBox`
    """
    theme = conditions.theme
    if theme.startswith("$"):
        for con in conditions:
            if _is_positional_match(con, match_field):
                return True
    else:
        if not theme:
            return False
        return match_field == theme.split(".", 1)[0]
    return False


def _perr_doc(val):
    """
    For pretty error msg, same as Mongo
    """
    v_lis = []
    for _k, _v in val.items():
        if isinstance(_v, string_type):
            v_lis.append("{0}: \"{1}\"".format(_k, _v))
        else:
            if is_mapping_type(_v):
                _v = _perr_doc(_v)
            if is_array_type(_v):
                _ = []
                for v in _v:
                    _.append(_perr_doc(v))
                _v = "[ " + ", ".join(_) + " ]"
            v_lis.append("{0}: {1}".format(_k, _v))
    return "{ " + ", ".join(v_lis) + " }"


class Projector(object):
    """
    """

    ARRAY_OP_NORMAL = 0
    ARRAY_OP_POSITIONAL = 1
    ARRAY_OP_ELEM_MATCH = 2

    def __init__(self, spec, query):
        self.proj_with_id = True
        self.include_flag = None
        self.regular_field = []
        self.array_field = {}

        self.parser(spec, query)

    def __call__(self, doc):
        """
        """
        field_walker = FieldWalker(doc)
        if not self.proj_with_id:
            del doc["_id"]

        for field_path in self.array_field:
            self.array_field[field_path](field_walker)

        if self.include_flag:
            self.regular_field += list(self.array_field.keys())
            self.inclusion(field_walker, self.regular_field)
        else:
            self.exclusion(field_walker, self.regular_field)

    def parser(self, spec, query):
        """
        """
        self.array_op_type = self.ARRAY_OP_NORMAL

        for key, val in spec.items():
            # Parsing options
            if is_mapping_type(val):
                if not len(val) == 1:
                    _v = _perr_doc(val)
                    raise OperationFailure(">1 field in obj: {}".format(_v))

                # Array field options
                sub_k, sub_v = next(iter(val.items()))
                if sub_k == "$slice":
                    if isinstance(sub_v, int):
                        # (NOTE) This is A-OK.
                        pass
                    elif is_array_type(sub_v):
                        if not len(sub_v) == 2:
                            raise OperationFailure("$slice array wrong size")
                        if sub_v[1] <= 0:
                            raise OperationFailure(
                                "$slice limit must be positive")
                    else:
                        raise OperationFailure(
                            "$slice only supports numbers and [skip, limit] "
                            "arrays")

                    self.array_field[key] = self.parse_slice()

                elif sub_k == "$elemMatch":
                    if not is_mapping_type(sub_v):
                        raise OperationFailure("elemMatch: Invalid argument, "
                                               "object required.")
                    if self.array_op_type == self.ARRAY_OP_POSITIONAL:
                        raise OperationFailure("Cannot specify positional "
                                               "operator and $elemMatch.")
                    if "." in key:
                        raise OperationFailure(
                            "Cannot use $elemMatch projection on a nested "
                            "field.")

                    self.array_op_type = self.ARRAY_OP_ELEM_MATCH

                    qfilter = QueryFilter(sub_v)
                    self.array_field[key] = self.parse_elemMatch(key, qfilter)

                elif sub_k == "$meta":
                    # Currently Not supported.
                    raise NotImplementedError("Monty currently not support "
                                              "$meta in projection.")

                else:
                    _v = _perr_doc(val)
                    raise OperationFailure(
                        "Unsupported projection option: "
                        "{0}: {1}".format(key, _v))

            elif key == "_id" and not _is_include(val):
                self.proj_with_id = False

            else:
                # Normal field options, include or exclude.
                flag = _is_include(val)
                if self.include_flag is None:
                    self.include_flag = flag
                else:
                    if not self.include_flag == flag:
                        raise OperationFailure(
                            "Projection cannot have a mix of inclusion and "
                            "exclusion.")

                self.regular_field.append(key)

            # Is positional ?
            bad_ops = [".$ref", ".$id", ".$db"]
            if ".$" in key and not any(ops in key for ops in bad_ops):
                # Validate the positional op.
                if not _is_include(val):
                    raise OperationFailure(
                        "Cannot exclude array elements with the positional "
                        "operator.")
                if self.array_op_type == self.ARRAY_OP_POSITIONAL:
                    raise OperationFailure(
                        "Cannot specify more than one positional proj. "
                        "per query.")
                if self.array_op_type == self.ARRAY_OP_ELEM_MATCH:
                    raise OperationFailure(
                        "Cannot specify positional operator and $elemMatch.")
                if ".$" in key.split(".$", 1)[-1]:
                    raise OperationFailure(
                        "Positional projection '{}' contains the positional "
                        "operator more than once.".format(key))
                conditions = query.conditions
                if not _is_positional_match(conditions, key.split(".", 1)[0]):
                    raise OperationFailure(
                        "Positional projection '{}' does not match the query "
                        "document.".format(key))

                self.array_op_type = self.ARRAY_OP_POSITIONAL

                self.array_field[key[:-2]] = self.parse_positional(key[:-2])

        if self.include_flag is None:
            self.include_flag = False

    def parse_slice(self):
        def _slice(field_walker):
            pass
        return _slice

    def parse_elemMatch(self, field_path, qfilter):
        def _elemMatch(field_walker):
            doc = field_walker.doc
            has_match = False
            if field_path in doc and is_array_type(doc[field_path]):
                # empty_array_error(doc[field_path])
                for emb_doc in doc[field_path]:
                    if qfilter(emb_doc):
                        doc[field_path] = [emb_doc]
                        has_match = True
                        break
            if not has_match:
                del field_walker.doc[field_path]

            if not self.include_flag:
                self.inclusion(field_walker, [field_path])

        return _elemMatch

    def parse_positional(self, field_path):
        def empty_array_error(array):
            if len(array) == 0:
                raise OperationFailure(
                    "Executor error during find command: BadValue: "
                    "positional operator ({}.$) requires corresponding "
                    "field in query specifier".format(field_path))

        def _positional(field_walker):
            if "." in field_path:
                fore_path, key = field_path.rsplit(".", 1)
                if field_walker(fore_path).exists:
                    for emb_doc in field_walker.value:
                        if is_array_type(emb_doc[key]):
                            empty_array_error(emb_doc[key])
                            emb_doc[key] = emb_doc[key][:1]
                        else:
                            del emb_doc[key]
            else:
                doc = field_walker.doc
                if field_path in doc:
                    if is_array_type(doc[field_path]):
                        empty_array_error(doc[field_path])
                        doc[field_path] = doc[field_path][:1]
                    else:
                        del doc[field_path]

        return _positional

    def drop_doc(self, field_walker, key):
        if field_walker.exists:
            for emb_doc in field_walker.value:
                if key in emb_doc:
                    del emb_doc[key]

    def inclusion(self, field_walker, include_field, fore_path=""):
        if fore_path:
            key_list = []
            for val in field_walker.value:
                if is_mapping_type(val):
                    key_list += list(val.keys())
            field_walker.reset()
            key_list = list(set(key_list))
        else:
            key_list = list(field_walker.doc.keys())

        if "_id" in key_list:
            key_list.remove("_id")

        for key in key_list:
            current_path = fore_path + key

            if current_path in include_field:
                # skip included field
                continue

            drop = True
            for field_path in include_field:
                if field_path.startswith(current_path):
                    drop = False
                    break

            if drop:
                if fore_path:
                    with field_walker(fore_path[:-1]):
                        self.drop_doc(field_walker, key)
                else:
                    if key in field_walker.doc:
                        del field_walker.doc[key]
            else:
                fore_path = current_path + "."
                with field_walker(current_path):
                    self.inclusion(field_walker, include_field, fore_path)

    def exclusion(self, field_walker, exclude_field):
        for field_path in exclude_field:
            if "." in field_path:
                fore_path, key = field_path.rsplit(".", 1)
                with field_walker(fore_path):
                    self.drop_doc(field_walker, key)
            else:
                if field_path in field_walker.doc:
                    del field_walker.doc[field_path]