"""
Provides transformations for tuple type hints into serializers.
"""

from ..serializers import Serializer, TupleSerializer
from ..type_checking import Any, TypeVar, annotated, get_tuple_args
from ..utils import StructuredAlias


def transform_tuple(unwrapped: Any, actual: Any) -> Any:
    for x in (actual, unwrapped):
        if tuple_args := get_tuple_args(x):
            if any(isinstance(arg, (TypeVar, StructuredAlias)) for arg in tuple_args):
                return StructuredAlias(tuple, tuple_args)
            extract = annotated(Serializer).extract
            serializers = tuple(map(extract, tuple_args))
            if all(serializers):
                # type-narrowing for most typecheckers doesn't occur on `all`
                return TupleSerializer(serializers)  # type: ignore


annotated.register_transform(transform_tuple)
