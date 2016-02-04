eucalyptus-imaging-worker
===================

What is this?
-------------

The *eucalyptus-imaging-service* is a service that is installed in the Eucalyptus
Imaging EMI.

Prerequisites
-------------

In order to use *eucalyptus-imaging-service*, you will need a few things:

* A Eucalyptus EMI on which to install the service
* ntp
* python-boto >= 2.8.0
* python-httplib2
* python-lxml
* python-m2ext
* python-requests
* sudo

Installing from the repository
------------------------------

To install the *eucalyptus-imaging-worker* package straight from the repository, run:

    $ ./install-worker.sh

This will create various directories and copy configuration files, as well as
create a *imaging-worker* user account.

Starting the worker
--------------------

The *eucalyptus-imaging-worker* service can be started by running:

    $ service eucalyptus-imaging-worker start

Please Note: This service will **not** work unless it is running on a Eucalyptus
instance that has been instantiated by the Eucalyptus Imaging service.

