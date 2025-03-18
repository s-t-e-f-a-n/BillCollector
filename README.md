# BillCollector

Let BillCollector collect your bills from different personalized web portals.

Invoices and documents that are regularly stored by service providers in the respective online account are automatically retrieved by BillCollector and stored locally in a download folder. The workflow really makes sense when the files are consumed in the download folder of Paperless ngx or a similar document management system (DMS).

BillCollector uses

- Vaultwarden as a vault for the access data for the online accounts
- Selenium (for Python) to automate the browser control
- Chrome for testing and Chromedriver as the browser front end of the service provider's online portal

Chrome is operated headless, so that BillCollector can do its job on a Raspberry PI or a NAS headless integrated into the cron-scheduler on a regular basis, e.g. retrieving the newest document twice a month.

Following diagram summarizes the complete BillCollector Ecosystem

![BillCollector Ecosystem](/doc/BillCollector.svg)

## How does it work?

Scheduled, for instance bi-monthly, your server's cron demon runs the BillCollector docker container which exposes a download folder to the server's file system. The docker container integrates Chrome for Testing, Chromedrivers and a Python with Selenium enfironment where the BillCollector application runs in.

For each container run, BillCollector walks thru a configuration file with the `List of Services`, gets the secret login data from Vaultwarden via the Bitwarden API, accesses the webservice via the Selenium Python API automating the Chrome browser access to the web service and aiming to download the latest document (e.g. your monthly mobile phone bill).

With a document-processing document management system (DMS) such as Paperless ngx in place, the downloaded file is forwarded directly to the DMS, where it is automatically analyzed, tagged and sorted into the local document database accordingly.

## Overview of the Prerequisites

Following services are needed to be in place for BillCollector:

- Docker environment
- Vaultwarden (docker image: vaultwarden/server:latest)
- ... with Bitwarden API (<https://bitwarden.com/help/vault-management-api/>) in one docker stack
- Secure https access is mandatory for account management and usage of Vaultwarden. Therefore, addtionally needed:
  - nginxproxymanager with Let's Encrypt (docker image: jc21 nginx-proxy-manager:latest)
  - Duckdns account & config -> redirect to local IP address

## Installation

### Docker Environment

It is assumed that you have a docker environment up and running. There are different options you can choose from: Docker Desktop on a Linux or Windows machine or for your Mac, docker on the command line of your NAS or your Raspberry Pi. Plenty ressources on the internet will support you getting that done. A natural good starting point is the [Docker Getting Started](https://docs.docker.com/get-started/).

I have it running on on my self-built Mini-ITX Intel Pentium J5040 NAS hardware equipped with the Debian Linux based NAS operating system  [openmediavault](https://www.openmediavault.org/) (OMV) and the [omv-extras](https://wiki.omv-extras.org/doku.php?id=omv7:docker_in_omv) installed.

### Vault of Secrets

BillCollector uses the selfhosted [Vaultwarden](https://github.com/dani-garcia/vaultwarden) password manager.

Why Vaultwarden? The simple reason is that it is a resource-light-weight alternative to Bitwarden and compatible with the Bitwarden Vault Mangement API integrated in the [Bitwarden CLI](https://github.com/tangowithfoxtrot/bw-docker) allowing to retrieve secret login data programmatically.

On [Vaultwarden Docker](https://github.com/s-t-e-f-a-n/Vaultwarden) you'll get the Vaultwarden and the Bitwarden CLI as a `Dockerfile` and a `docker-compose.yml`. Follow the installation guide over there.

### Enabling DNS and HTTPS with Let's Encrypt certs

**This configuration will not only support your BillCollector setup, but is also quite cool for an improved user experience when accessing all your other locally running dockerized web services: You can get rid of a accessing them by IP address / port combinations. Instead, you can set domain names for each of the services and enable HTTPS access to them, which avoids a bad user experience as they usually only want to allow secure access to each website these days.**

Vaultwarden only allows secure HTTPS access by default. Suppose you want to run an instance of Vaultwarden that can only be accessed from your local network by name instead of IP adress and you want your instance to be HTTPS-enabled with certs signed by a widely accepted Certificate Authority (CA) instead of managing your own private CA.

Currently the simplest option is offered by [Duck DNS](https://www.duckdns.org) as a free Domain Name Service (DNS) in combination with the locally dockerized [Nginx Proxy Manager](https://nginxproxymanager.com/) (NPM) enabling address forwarding to your Vaultwarden instance including free SSL using the [Let's Encrypt](https://letsencrypt.org/) CA.

The cool things about DuckDNS is not only that it is free of charge, but that it also allows wildcard domains and local IP address names. For the latter, however, DNS rebind protection must also be set up in your router. Moreover, the big benefit is, that you do not need to open your router to the internet by Port Forwarding! 😄

The only downside of Duck DNS is, that you cannot freely choose your domainname because it will follow the name scheme [https://\<your subdomain\>.duckdns.org](duckdns.org).

Steps to follow:

1. If you don't already have an account, create one at <https://www.duckdns.org/>. Define a subdomain name either used as a wildcard domain (e.g., my-domain.duckdns.org) or just a single domain name for your Vaultwarden instance (e.g., my-vw.duckdns.org) and set its IP to your vaultwarden host's private IP (e.g., 192.168.1.100). Make note of your account's token (a string in UUID format). NPM will need this token to solve the DNS challenge (step 4. below)

    ![MyDuckDNS](/doc/Screenshot%202025-02-27%20234458.jpg)

2. Configure the DNS Rebind Protection in your router: For a Fritz!Box routers go to `/Heimnetz/Netzwerk/Netzwerkeinstellungen/DNS-Rebind-Schutz` and enter the hostname you configured in Duck DNS [\<your subdomain\>.duckdns.org](duckdns.org).

3. Check the setup of your domainname was successful.
On your Windows machine `<WIN>R cmd` and enter `nslookup <your subdomain\>.duckdns.org`. The response should look similar as follows:

    ![nslookup](/doc/Screenshot%202025-02-28%20002726.jpg)

    Alternatively on your Linux machine use a tool like `dig` to check Duck DNS is resolving your domainname.

4. Now we are ready to install NPM from the guide at the [Nginx Proxy Manager](https://nginxproxymanager.com).

   a. After you've run your NPM container the first time, enter the web ui using the default credentials and change them to your private ones.

   b. Go to `SSL Certificates`, Press `Add SSL Certificate` and choose `Let's Encrypt`.
      - In the form fill in the field `Domain Names` either with wildcard like `*.my-dowmain.duckdns.org` and `my-domain.duckdns.org` or just a single domain like `my-vw.duckdns.org` from your Duck DNS configuration in step 1.
      - In the same form fill in the field `Email address for Let's Encrypt` you want Let`s Encrypt to link the certificates in their database with.
      - Enable the switch `Use DNS Challenge`, choose `DuckDNS`from the list and enter the token from step 1. into the text box by replacing `your-duckdns-token` in `dns_duckdns_token=your-duckdns-token` accordingly.
      - You may leave blank `Propagation Seconds` or fill in a number of seconds to wait for DNS propagation, before it fails.
      - Enable the switch `I agree...` and press `Save`
      - Now it may take some seconds to finalize the Let's  Encrypt DNS Challenge.
      - When finished successfully a new SSL certificate is configured with an expiry in some months which will be updated automatically by your NPM.

   c. Go to `Hosts`, choose `Proxy Hosts` and Press `Add Proxy Host`.
      - In the form of tab `Details` fill in the domainname you want to access Vaultwarden locally, like `vault.my-domain.duckdns.org` (using your wildcard domain) or `my-vw.duckdns.org` (just the single domain from step 1.).
      - In the same form fill `Scheme`with `http`, `Forward Hostname/IP` with the IP address of your Vaultwarden Host (i.e. the IP of your Host running the docker on in your lcoal environment) and the `Forward Port` of your Vaultwarden docker container's port mapping to the container's port `80` (refer to the `docker-compose.yml of [Vault of Secrets](#vault-of-secrets))
      - In the form of tab `SSL` enter the SSL certificate name(s) configured in step b. and enable the switches `Force SSL` and `HTTP/2 Support`.
      - Pres `Save`

   d. Test the accessiblity of your Vaultwarden Web UI in your browser by entering [https://vault.my-domain.duckdns.org](https://vault.my-domain.duckdns.org) or [https://my-vw.duckdns.org](https://my-vw.duckdns.org) dependent on your configuration. You should be presented the page for creating a new Vaultwarden account on a successful NPM installation and configuration now.

### Time for the BillCollector Installation

Now, that you have done a good job installing the prerequisites, we are focussing on installing the BillCollector docker which is simple as follows:

1. Download this git repository to a folder in your local docker environment assuming a Linux bash terminal, e.g. `git clone \<URL\>/stefan/BillCollector.git`

2. [Configure BillCollector](#configure-billcollector) needs to be done. After each change in configuration proceed again with step 3.

3. Open the installation script in your editor, e.g. `nano ./install_docker-image.sh`, adapt the link to your `Paperless ngx` instance's consumption folder (`ln -s </path/to/your/paperless/inbox>/ Downloads`) and save it.

4. On your Linux console enter `./install_docker-image.sh` which creates a new docker image `billcollector:latest` and sets the soft link to the inbox of your `Paperless ngx` inbox to let BillCollector output retrieved bills from the web services directly to your DMS.

5. Let your server's cron call your BillCollector periodically (e.g. bi-monthly) by calling `</path/to/your/billcollector-git-clone-folder/BillCollector.sh bc_default.ini`.

## Configure BillCollector

First and once, for the basic configuration you need to adapt the `.env` file located in the `/apps` folder:
  
- `VAULT_HOST=<hostname of your vault e.g. vault.my-domain.duckdns.org>`
- `BW_API_URL=<http/https-URL of the bitwarden API e.g. http://<local-ip>:8087>`

The BillCollector configuration for each web service from which you want to retrieve documents consists of three parts:

1. Your private web service's login data to be created in Vaultwarden as entries:
   - `name`: name of the web service
   - `user name`: your secret login name to the web service
   - `password`: your secret password to the web service
   - (optional and dependent on the web service) `TOTP`: key from your web service
   - `URI 1`: the web service`s web address where BillCollector should start from

2. BillCollector's name of services list in `/apps/bc_default.ini`:
   - enter line by line the name of the web service matching the `name` of the service`s entry in Vaultwarden
   - for web services where you have more than one login data for (e.g. family members having different accounts at the same mobile phone provider) you can enter the line in following format: `<name of service> [<user name 1>, <user name 2>...]`. BillCollector will then cycle thru the list of user names and automatically logs into each user's account at the service.

3. The recipe or cookbook of browser automation from login to download of the wanted document from the web service. Currently this recipe is located in the Python source code of `/apps/BillCollectorServices.py`. 😨😨😨
