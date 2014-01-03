imaging-servo
===================

What is this?
-------------

The *imaging-servo* is a service that is installed in the Eucalyptus
Imaging EMI.

Prerequisites
-------------

In order to use *imaging-servo*, you will need a few things:

* A Eucalyptus EMI on which to install the service
* ntp
* python-boto >= 2.8.0
* python-httplib2
* sudo

Installing from the repository
------------------------------

To install the *imaging-servo* package straight from the repository, run:

    $ ./install-servo.sh

This will create various directories and copy configuration files, as well as
create a *servo* user account.

Starting the service
--------------------

The *imaging-servo* service can be started by running:

    $ service imaging-servo start

Please Note: This service will **not** work unless it is running on a Eucalyptus
instance that has been instantiated by the Eucalyptus Balancer service.

