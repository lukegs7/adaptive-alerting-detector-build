import json
import logging
import requests
import time
import datetime
import related
from .factory import build_detector
from .exceptions import DetectorBuilderError

from adaptive_alerting_detector_build.config import MODEL_SERVICE_URL, MODEL_SERVICE_USER
from adaptive_alerting_detector_build.detectors import Detector, DetectorUUID, get_detector_class
from adaptive_alerting_detector_build.detectors.mapping import DetectorMapping, build_metric_detector_mapping


LOGGER = logging.getLogger(__name__)


CREATE_DETECTOR_TIMEOUT = 60


class DetectorBuilderClientError(DetectorBuilderError):
    """Base class for detector builder client errors."""



class DetectorClient:
    def __init__(self, model_service_url=None, model_service_user=None, **kwargs):
        if model_service_url:
            self._url = model_service_url
        elif MODEL_SERVICE_URL:
            self._url = MODEL_SERVICE_URL
        else:
            raise ValueError("model_service_url not found.")

        if model_service_user:
            self._user = model_service_user
        elif MODEL_SERVICE_USER:
            self._user = MODEL_SERVICE_USER
        else:
            raise ValueError("model_service_user not found.")
            

    def get_detector(self, detector_uuid):
        response = requests.get(
            f"{self._url}/api/v2/detectors/findByUuid?uuid={detector_uuid}"
        )
        response.raise_for_status()
        detector = related.from_json(response.text, Detector)
        detector_class = get_detector_class(detector.type)
        return related.from_json(response.text, detector_class)

    def list_detectors_for_metric(self, metric_tags):
        response = requests.post(
            f"{self._url}/api/detectorMappings/findMatchingByTags",
            json=[metric_tags],
        )
        response.raise_for_status()
        detectors = list()
        grouped_detectors_by_search_index = response.json()["groupedDetectorsBySearchIndex"]
        if grouped_detectors_by_search_index:
            for detector in grouped_detectors_by_search_index["0"]:
                detectors.append(self.get_detector(detector["uuid"]))
        return detectors

    def list_detector_mappings(self, detector_uuid):
        response = requests.post(
            f"{self._url}/api/detectorMappings/search",
            json={ "detectorUuid": detector_uuid }
        )
        response.raise_for_status()
        detector_mappings = list()
        for detector_mapping in response.json():
            detector_mappings.append(related.from_json(json.dumps(detector_mapping), DetectorMapping))
        return detector_mappings

    def save_metric_detector_mapping(self, detector_uuid, metric):
        """
        Detectors can't be managed without looking up by a metric, so the only way to
        create a detector is to lookup the metric first and see that it doesn't exist.
        If a detector already exists for metric, DetectorBuilderError is raised.
        """
        metric_detector_mapping = build_metric_detector_mapping(detector_uuid, metric)
        create_metric_detector_mapping = requests.post(
            f"{self._url}/api/detectorMappings", json=related.to_dict(metric_detector_mapping),
            timeout=30
        )
        create_metric_detector_mapping.raise_for_status()

    def delete_metric_detector_mapping(self, detector_mapping_id):
        """
        Detectors can't be managed without looking up by a metric, so the only way to
        create a detector is to lookup the metric first and see that it doesn't exist.
        If a detector already exists for metric, DetectorBuilderError is raised.
        """
        response = requests.delete(
            f"{self._url}/api/detectorMappings?id={detector_mapping_id}",
            timeout=30
        )
        response.raise_for_status()

    def create_detector(self, detector):
        """
        Detectors can't be managed without looking up by a metric, so the only way to
        create a detector is to lookup the metric first and see that it doesn't exist.
        If a detector already exists for metric, DetectorBuilderError is raised.
        """
        create_detector_request = related.to_dict(detector, suppress_empty_values=True)
        create_detector_response = requests.post(
            f"{self._url}/api/v2/detectors", json=create_detector_request,
            timeout=30
        )
        create_detector_response.raise_for_status()
        detector_uuid = create_detector_response.text
        create_detector_start = datetime.datetime.now()
        create_detector_elapsed = create_detector_start - datetime.datetime.now()
        detector = None
        while not detector and create_detector_elapsed.total_seconds() < CREATE_DETECTOR_TIMEOUT:
            time.sleep(1.0)
            detector = self.get_detector(detector_uuid)
            create_detector_elapsed = datetime.datetime.now() - create_detector_start
        if detector:
            return detector
        else:
            raise DetectorBuilderClientError(f"Timeout waiting for detector uuid '{detector_uuid}' to be available from model service.")

    def update_detector(self, detector):
        """
        * The service requires 'type' on update, but we treat it as immutable.
        * If values for 'detector_config', 'enabled', or 'trusted' are not passed, the
          current value is used.
        """
        response = requests.put(
            f"{self._url}/api/v2/detectors?uuid={detector.uuid}", json=related.to_dict(detector), timeout=30
        )
        response.raise_for_status()
        return self.get_detector(detector.uuid)

    def delete_detector(self, detector_uuid):
        """

        """
        response = requests.delete(
            f"{self._url}/api/v2/detectors?uuid={detector_uuid}", timeout=30
        )
        response.raise_for_status()


    def create_metric_detector(self, detector, metric):
        """
        
        """
        new_detector = self.create_detector(detector)
        self.save_metric_detector_mapping(new_detector.uuid, metric)


    def delete_metric_detector(self, detector_uuid):
        """
        
        """
        response = requests.delete(
            f"{self._url}/api/v2/detectors?uuid={detector_uuid}", timeout=30
        )
        response.raise_for_status()