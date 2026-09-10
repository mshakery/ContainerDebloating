from __future__ import annotations

from replication.runner.base import SubjectSpec
from replication.workloads import datastore, http_service, oneshot


SUBJECTS: list[SubjectSpec] = [

    SubjectSpec("nginx",       "library/nginx",        "latest", "general-purpose", http_service.make_nginx),
    SubjectSpec("node",        "library/node",         "latest", "general-purpose", http_service.make_node_http),
    SubjectSpec("php-apache",  "library/php",          "apache", "general-purpose", http_service.make_php_apache),
    SubjectSpec("openresty",   "openresty/openresty",  "latest", "general-purpose", http_service.make_openresty),


    SubjectSpec("alpine",             "library/alpine", "latest",      "cold-start-base", oneshot.make_alpine),
    SubjectSpec("busybox",            "library/busybox","latest",      "cold-start-base", oneshot.make_busybox),
    SubjectSpec("python-3.12-alpine", "library/python", "3.12-alpine", "cold-start-base", oneshot.make_python_alpine),
    SubjectSpec("node-20-alpine",     "library/node",   "20-alpine",   "cold-start-base", oneshot.make_node_alpine),


    SubjectSpec("rocker-r-ver", "rocker/r-ver",          "latest", "machine-learning", oneshot.make_rocker_r_ver),
    SubjectSpec("r-base",       "library/r-base",        "latest", "machine-learning", oneshot.make_r_base),
    SubjectSpec("tensorflow",   "tensorflow/tensorflow", "latest", "machine-learning", oneshot.make_tensorflow),
    SubjectSpec("pytorch",      "pytorch/pytorch",       "latest", "machine-learning", oneshot.make_pytorch),


    SubjectSpec("influxdb",  "library/influxdb",  "latest", "data-intensive", datastore.make_influxdb),
    SubjectSpec("memcached", "library/memcached", "latest", "data-intensive", datastore.make_memcached),
    SubjectSpec("neo4j",     "library/neo4j",     "latest", "data-intensive", datastore.make_neo4j),
    SubjectSpec("cassandra", "library/cassandra", "latest", "data-intensive", datastore.make_cassandra),
]

SUBJECTS_BY_ID: dict[str, SubjectSpec] = {s.id: s for s in SUBJECTS}
