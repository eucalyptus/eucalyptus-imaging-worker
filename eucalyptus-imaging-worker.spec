%{!?python_sitelib: %global python_sitelib %(%{__python} -c "from distutils.sysconfig import get_python_lib; print(get_python_lib())")}

Name:           eucalyptus-imaging-worker
Version:        %{build_version}
Release:        0%{?build_id:.%build_id}%{?dist}
Summary:        Configuration tool for the Eucalyptus Imaging Service

Group:          Applications/System
License:        GPLv3 
URL:            http://www.eucalyptus.com
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-root-%(%{__id_u} -n)

BuildArch:      noarch

BuildRequires:  python%{?__python_ver}-devel
BuildRequires:  python%{?__python_ver}-setuptools

Requires:       python%{?__python_ver}
Requires:       python%{?__python_ver}-boto
Requires:       python%{?__python_ver}-httplib2
Requires:       python-lxml
Requires:       python-requests
Requires:       python-m2ext
Requires:       sudo
Requires:       ntp
Requires:       ntpdate
Requires(pre):  %{_sbindir}/useradd

%description
Configuration tool for the Eucalyptus Imaging Service

%prep
%setup -q -n %{name}-%{version}%{?tar_suffix}

%build
# Build CLI tools
%{__python} setup.py build

%install
rm -rf $RPM_BUILD_ROOT

# Install CLI tools
%{__python} setup.py install -O1 --skip-build --root $RPM_BUILD_ROOT

#
# There is no extension on the installed sudoers file for a reason
# It will only be read by sudo if there is *no* extension
#
install -p -m 0440 -D scripts/worker-sudo.conf $RPM_BUILD_ROOT/%{_sysconfdir}/sudoers.d/worker
install -p -m 755 -D scripts/imaging-worker-init $RPM_BUILD_ROOT/%{_initddir}/imaging-worker
install -p -m 755 -D scripts/worker-ntp-update $RPM_BUILD_ROOT%{_libexecdir}/%{name}/ntp-update
install -m 6700 -d $RPM_BUILD_ROOT/%{_var}/{run,lib,log}/imaging-worker

%clean
rm -rf $RPM_BUILD_ROOT

%pre
getent passwd servo >/dev/null || \
    useradd -d %{_var}/lib/imaging-worker \
    -M -s /sbin/nologin servo

# Stop running services for upgrade
if [ "$1" = "2" ]; then
    /sbin/service imaging-worker stop 2>/dev/null || :
fi

%files
%defattr(-,root,root,-)
%doc README.md LICENSE
%{python_sitelib}/*
%{_bindir}/imaging-worker
%{_sysconfdir}/sudoers.d/worker
%{_initddir}/imaging-worker
%{_libexecdir}/%{name}
%config(noreplace) %{_sysconfdir}/cron.d/%{name}

%defattr(-,worker,worker,-)
%dir %{_sysconfdir}/imaging-worker
%dir %{_var}/run/imaging-worker
%dir %{_var}/log/imaging-worker
%dir %{_var}/lib/imaging-worker
%config(noreplace) %{_sysconfdir}/imaging-worker/boto.cfg

%changelog
* Sat Feb 22 2014 Eucalyptus Release Engineering <support@eucalyptus.com> - 1.0.0-0
- Initial build
