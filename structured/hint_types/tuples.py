"""
Provides transformations for tuple type hints into serializers.
"""

from ..serializers import Serializer, TupleSerializer
from ..type_checking import Any, TypeVar, annotated, get_tuple_args, istuple, Tuple
from ..utils import StructuredAlias


def transform_tuple(base_type: Any, hint: Any) -> Any:
    if istuple(base_type):
        if tuple_args := get_tuple_args(base_type):
            if any(isinstance(arg, (TypeVar, StructuredAlias)) for arg in tuple_args):
                return StructuredAlias(Tuple, tuple_args)
            serializers = [annotated.transform(x) for x in tuple_args]
            if all(isinstance(x, Serializer) for x in serializers):
                return TupleSerializer(serializers)


annotated.register_transform(transform_tuple)
