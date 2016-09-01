import os
import json
import signal

from twisted.python.filepath import FilePath
from ooni.utils import log
from ooni.utils.files import directory_usage
from ooni.settings import config

class MeasurementInProgress(Exception):
    pass

class Process():
    supported_tests = [
        "web_connectivity",
        "http_requests"
    ]
    @staticmethod
    def web_connectivity(entry):
        result = {}
        result['anomaly'] = False
        if entry['test_keys']['blocking'] is not False:
            result['anomaly'] = True
        result['url'] = entry['input']
        return result

    @staticmethod
    def http_requests(entry):
        result = {}
        test_keys = entry['test_keys']
        anomaly = (
            test_keys['body_length_match'] and
            test_keys['headers_match'] and
            (
                test_keys['control_failure'] !=
                test_keys['experiment_failure']
            )
        )
        result['anomaly'] = anomaly
        result['url'] = entry['input']
        return result

def generate_summary(input_file, output_file):
    results = {}
    with open(input_file) as in_file:
        for idx, line in enumerate(in_file):
            entry = json.loads(line.strip())
            result = {}
            if entry['test_name'] in Process.supported_tests:
                result = getattr(Process, entry['test_name'])(entry)
            result['idx'] = idx
            results['test_name'] = entry['test_name']
            results['test_start_time'] = entry['test_start_time']
            results['country_code'] = entry['probe_cc']
            results['asn'] = entry['probe_asn']
            results['results'] = results.get('results', [])
            results['results'].append(result)

    with open(output_file, "w") as fw:
        json.dump(results, fw)

class MeasurementNotFound(Exception):
    pass

def get_measurement(measurement_id, compute_size=False):
    size = -1
    measurement_path = FilePath(config.measurements_directory)
    measurement = measurement_path.child(measurement_id)
    if not measurement.exists():
        raise MeasurementNotFound

    running = False
    completed = True
    keep = False
    stale = False
    if measurement.child("measurements.njson.progress").exists():
        completed = False
        # XXX this is done quite often around the code, probably should
        # be moved into some utility function.
        pid = measurement.child("running.pid").open("r").read()
        pid = int(pid)
        try:
            os.kill(pid, signal.SIG_DFL)
            running = True
        except OSError:
            stale = True

    if measurement.child("keep").exists():
        keep = True

    if compute_size is True:
        size = directory_usage(measurement.path)

    test_start_time, country_code, asn, test_name = \
        measurement_id.split("-")[:4]
    return {
        "test_name": test_name,
        "country_code": country_code,
        "asn": asn,
        "test_start_time": test_start_time,
        "id": measurement_id,
        "completed": completed,
        "keep": keep,
        "running": running,
        "stale": stale,
        "size": size
    }


def get_summary(measurement_id):
    measurement_path = FilePath(config.measurements_directory)
    measurement = measurement_path.child(measurement_id)

    if measurement.child("measurements.njson.progress").exists():
        raise MeasurementInProgress

    summary = measurement.child("summary.json")
    if not summary.exists():
        generate_summary(
            measurement.child("measurements.njson").path,
            summary.path
        )

    with summary.open("r") as f:
        return json.load(f)


def list_measurements(compute_size=False):
    measurements = []
    measurement_path = FilePath(config.measurements_directory)
    for measurement_id in measurement_path.listdir():
        try:
            measurements.append(get_measurement(measurement_id, compute_size))
        except:
            log.err("Failed to get metadata for measurement {0}".format(measurement_id))
    return measurements

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: {0} [input_file] [output_file]".format(sys.argv[0]))
        sys.exit(1)
    generate_summary(sys.argv[1], sys.argv[2])