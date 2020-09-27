from rest_framework.serializers import Serializer
from pss_project.api.serializers.rest.metadata.MetadataSerializer import MetadataSerializer
from pss_project.api.serializers.fields.UnixEpochDatetimeField import UnixEpochDateTimeField
from pss_project.api.serializers.rest.parameters.MicrobenchmarkParametersSerializer import (
    MicrobenchmarkParametersSerializer)
from pss_project.api.serializers.rest.metrics.MicrobenchmarkMetricsSerializer import MicrobenchmarkMetricsSerializer
from pss_project.api.models.rest.MicrobenchmarkRest import MicrobenchmarkRest


class MicrobenchmarkSerializer(Serializer):
    # Fields
    metadata = MetadataSerializer()
    timestamp = UnixEpochDateTimeField()
    parameters = MicrobenchmarkParametersSerializer()
    metrics = MicrobenchmarkMetricsSerializer(many=True)

    def create(self, validated_data):
        return MicrobenchmarkRest(**validated_data)
