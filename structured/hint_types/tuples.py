"""
Provides transformations for tuple type hints into serializers.
"""

from ..serializers import Serializer, TupleSerializer
from ..type_checking import Any, annotated, get_tuple_args


def transform_tuple(unwrapped: Any, actual: Any) -> Any:
    for x in (actual, unwrapped):
        if tuple_args := get_tuple_args(x):
            extract = annotated(Serializer).extract
            serializers = tuple(map(extract, tuple_args))
            if all(serializers):
                # type checker doesn't know all==True means none are None
                return TupleSerializer(serializers)  # type: ignore


annotated.register_transform(transform_tuple)
