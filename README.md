# BillCollector

![BillCollector EyeCatcher](/doc/BillCollector_EyeCatcher.jpg)

## Table of Contents

- [What is BillCollector?](#what-is-billcollector)
- [How does it work?](#how-does-it-work)
- [Contributing](#contributing)
- [Quick Start](#quick-start)
  - [Docker Environment](#docker-environment)
  - [Vault of Secrets](#vault-of-secrets)
  - [Enabling DNS and HTTPS with Let's Encrypt certs](#enabling-dns-and-https-with-lets-encrypt-certs)
  - [The BillCollector Installation](#the-billcollector-installation)
- [Configure BillCollector](#configuration)

## What is BillCollector?

> BillCollector is the automated front end for processing important documents in personal web portals that previously had to be tediously downloaded by hand.
>
> Invoices and documents that are regularly stored by service providers in the respective online account are automatically retrieved by BillCollector and stored locally in a download folder from where it may be consumed by a document management system like Paperless-ngx.

BillCollector uses:

- Vaultwarden as a safe vault of the login data for the online accounts
- Chrome for testing and Chromedriver as the browser front end of the service provider's online portal
- Selenium (for Python) to automate the browser control

Chrome is operated headless by default, so that BillCollector can do its job on a Raspberry PI or a NAS, headless integrated into the cron-scheduler on a regular basis.

Following diagram depicts the complete BillCollector Ecosystem:

![BillCollector Ecosystem](/doc/BillCollector.svg)

## How does it work?

Scheduled, for instance, bi-monthly, your server's cron daemon runs the BillCollector docker container which exposes a download folder to the server's file system. The docker container integrates Chrome and Chromedriver to interact with the service provider's online portal.

For each container run, BillCollector scripts the `List of Services`, gets the secret login data from Vaultwarden via the Bitwarden API, accesses the web service via the configured Selenium recipes, and downloads the documents.

With a document-processing document management system (DMS) such as Paperless ngx in place, the downloaded file is consumed, automatically analyzed, tagged, and sorted.

## Contributing

### How You Can Help

- **Star this project** on GitHub.
- **Share** it with your network.
- **Contribute** recipes for more web services - see how to [Configure BillCollector](#configuration) and get familiar with the YAML recipes.
- **Discuss** your ideas for improvements, more use cases and any comments by leaving notes in the Discussion area.

> 💡 **Tip**  
> Make yourself familiar with the concept of finding web elements. BillCollector takes advantage of Selenium and its methods for retrieving and controlling web elements.  
> [Selenium WebDriver Elements Documentation](https://www.selenium.dev/documentation/webdriver/elements/) is a good starting point.

## Quick Start

BillCollector requires the following services:

- Docker environment
- Vaultwarden (docker image: vaultwarden/server:latest) with Bitwarden API (<https://bitwarden.com/help/vault-management-api/>) in one docker stack
- Secure HTTPS access for account management and usage of Vaultwarden with:
  - nginxproxymanager with Let's Encrypt (docker image: jc21/nginx-proxy-manager:latest)
  - Duckdns account & config -> redirect to local IP address

### Docker Environment

It is assumed that you have a docker environment up and running. There are different options you can choose from: Docker Desktop on a Linux or Windows machine or for your Mac, docker on the command line, etc.

I have it running on my self-built Mini-ITX Intel Pentium J5040 NAS hardware equipped with the Debian Linux based NAS operating system [openmediavault](https://www.openmediavault.org/) (OMV).

### Vault of Secrets

BillCollector uses the self-hosted [Vaultwarden](https://github.com/dani-garcia/vaultwarden) password manager.

Why Vaultwarden?

1. It is a resource-light-weight alternative to Bitwarden.
2. It is compatible with the Bitwarden Vault Management API integrated in the [Bitwarden CLI](https://github.com/bitwarden/cli) which BillCollector uses for login data retrieval.
3. It stores your login data safely.
4. It is feature-rich, including the management of Time-Based One-Time (TOTP) passwords.

> 💡 **Tip**  
> On [Vaultwarden Docker](https://github.com/s-t-e-f-a-n/Vaultwarden), you'll get the Vaultwarden and the Bitwarden CLI as a `Dockerfile` and a `docker-compose.yml`. Follow the installation guide over there.

### Enabling DNS and HTTPS with Let's Encrypt certs

> 💡 **Tip**  
> This configuration will not only support your BillCollector setup but also improves the user experience when accessing all your other locally running dockerized web services:**

Vaultwarden only allows secure HTTPS access by default. Suppose you want to run an instance of Vaultwarden that can only be accessed from your local network by name instead of IP address and you want to use Let's Encrypt certificates.

Currently, the simplest option is offered by [Duck DNS](https://www.duckdns.org) as a free Domain Name Service (DNS) in combination with the locally dockerized [Nginx Proxy Manager](https://nginxproxymanager.com).

The cool thing about DuckDNS is not only that it is free of charge but also that it allows wildcard domains and local IP address names. For the latter, however, DNS rebind protection must also be configured in your router.

The only downside of Duck DNS is that you cannot freely choose your domain name because it will follow the naming scheme [https://\<your subdomain\>.duckdns.org](duckdns.org).

Steps to follow:

1. If you don't already have an account, create one at <https://www.duckdns.org/>. Define a subdomain name either used as a wildcard domain (e.g., my-domain.duckdns.org) or just a single domain name.

   ![MyDuckDNS](/doc/Screenshot%202025-02-27%20234458.jpg)

2. Configure the DNS Rebind Protection in your router: For Fritz!Box routers go to `/Heimnetz/Netzwerk/Netzwerkeinstellungen/DNS-Rebind-Schutz` and enter the hostname you configured in Duck DNS.

3. Check the setup of your domain name was successful.
   On your Windows machine `<WIN>R cmd` and enter `nslookup <your subdomain\>.duckdns.org`. The response should look similar as follows:

   ![nslookup](/doc/Screenshot%202025-02-28%20002726.jpg)

   Alternatively, on your Linux machine use a tool like `dig` to check Duck DNS is resolving your domain name.

4. Now we are ready to install NPM from the guide at the [Nginx Proxy Manager](https://nginxproxymanager.com).

   a. After you've run your NPM container the first time, enter the web UI using the default credentials and change them to your private ones.

   b. Go to `SSL Certificates`, Press `Add SSL Certificate` and choose `Let's Encrypt`.
      - In the form fill in the field `Domain Names` either with wildcard like `*.my-domain.duckdns.org` and `my-domain.duckdns.org` or just a single domain like `my-vw.duckdns.org`.
      - In the same form fill in the field `Email address for Let's Encrypt` you want Let's Encrypt to link the certificates in their database with.
      - Enable the switch `Use DNS Challenge`, choose `DuckDNS` from the list and enter the token from step 1 into the text box by replacing `your-duckdns-token` in `dns_duckdns_token=your-duckdns-token`.
      - You may leave `Propagation Seconds` blank or fill in a number of seconds to wait for DNS propagation before it fails.
      - Enable the switch `I agree...` and press `Save`.
      - Now it may take some seconds to finalize the Let's Encrypt DNS Challenge.
      - When finished successfully, a new SSL certificate is configured with an expiry in some months which will be updated automatically by your NPM.

   c. Go to `Hosts`, choose `Proxy Hosts`, and Press `Add Proxy Host`.
      - In the form of tab `Details` fill in the domain name you want to access Vaultwarden locally, like `vault.my-domain.duckdns.org` (using your wildcard domain) or `my-vw.duckdns.org`.
      - In the same form fill `Scheme` with `http`, `Forward Hostname/IP` with the IP address of your Vaultwarden Host (i.e., the IP of your Host running the docker in your local environment), and `Forward Port` with the port Vaultwarden is listening on (typically 80 for HTTP).
      - In the form of tab `SSL` enter the SSL certificate name(s) configured in step b. and enable the switches `Force SSL` and `HTTP/2 Support`.
      - Press `Save`.

   d. Test the accessibility of your Vaultwarden Web UI in your browser by entering [https://vault.my-domain.duckdns.org](https://vault.my-domain.duckdns.org) or [https://my-vw.duckdns.org](https://my-vw.duckdns.org).

### The BillCollector Installation

Now that we have done a good job installing all the prerequisites, we are focusing on installing the BillCollector docker which is as simple as follows:

1. Download this git repository to a folder in your local docker environment assuming a Linux bash terminal, e.g., `git clone <URL>/stefan/BillCollector.git`.

2. [Configure BillCollector](#configuration) needs to be done. After each change in configuration proceed again with step 3.

3. Open the installation script in your editor, e.g., `nano ./install_docker-image.sh`, adapt the link to your `Paperless ngx` instance's consumption folder (`ln -s </path/to/your/paperless/inbox>`).

4. On your Linux console enter `./install_docker-image.sh` which creates a new docker image `billcollector:latest` and sets the soft link to the inbox of your `Paperless ngx` to let BillCollector collect bills periodically.

5. Let your server's cron call your BillCollector periodically (e.g., bi-monthly) by calling `</path/to/your/billcollector-git-clone-folder/BillCollector.sh bc_default.ini`.

## Configuration

First and once, for the basic configuration you need to adapt the `.env` file located in the `/apps` folder:
  
- `VAULT_HOST=<hostname of your vault e.g., vault.my-domain.duckdns.org>`
- `BW_API_URL=<http/https-URL of the bitwarden API e.g., http://<local-ip>:8087>`

The BillCollector configuration for each web service from which you want to retrieve documents consists of three parts:

1. A Vaultwarden entry provides the login data for each of your private web service login:
   - `Name`: name of the web service
   - `User Name`: your secret login name to the web service
   - `Password`: your secret password to the web service
   - (optional and dependent on the web service) `TOTP`: key from your web service
   - `URI 1`: the web service's web address where BillCollector should start from

2. A list of service entries in `/apps/bc_default.ini` represents the script for collecting all bills:
   - Enter line by line the name of the web service matching the `Name` of the service's entry in Vaultwarden (1).
   - For web services where you have more than one login data for (e.g., family members having different accounts at the same mobile phone provider) you can enter the line in the following format: `<Name of web service> [<your name>, <additional name>]`.

     *Example ini script:*

     ```text
     winSIM [Dieter, Auto, Will, Anna]
     KabelDeutschland
     Lichtblick [Strom, Gas]
     ```

3. A YAML recipe defines the browser automation, which typically starts at login and ends at the download of the wanted document from the web service portal:
   - The recipes are placed in the subfolder `bc-recipes` and follow the naming convention `bc-recipe__<Name of web service>.yaml` where `Name of web service>` must equal `Name` of the web service in Vaultwarden.
   - The basic concept of the BillCollector recipes is summarized as follows:
      - YAML format
      - One recipe per web portal identified by the yaml element `serviceName` and its filename `bc-recipe__<serviceName>`.
      - Each recipe is structured in steps of actions.
      - Each action step is led by an actionType defining a specific (selenium) web element action from Click, ClickShadow, SendKeys, and Download.
      - Each action step is followed by parameters, namely (selenium) web element locators, variables, and specific controls.
         - Locators are a single or multiple pairs of (selenium) selectors (`ID`, `CSS_SELECTOR`, `XPATH`, `LINK_TEXT`) and web elements to be located.
         - Variables are `{USERNAME}`, `{PASSWORD}` or `{OTP}` (all three from vaultwarden linked to the web service) or the key `ENTER`.
         - Specific controls are `timeout` and `graceful`.
      - There is a YAML schema named `bc-recipe-schema.yml` which includes the rules to be followed by the YAML recipes.

> 💡 **Tip**  
> When creating new recipes, make use of AI, e.g., let yourself be helped by Copilot - that speeds up creating the YAML recipe 🚀.
> `BillCollectorRecipes.py` is used by `BillCollector` but also can be used as a separate command line tool for checking new YAML recipes:
> `Usage: python3 BillCollectorRecipes.py <recipes.yaml> [<schema.yaml>]`.
>
> Make use of the [Selenium IDE browser plugin](https://www.seleniumhq.org/selenium-ide). It lets you walk through your web portal to create a draft recipe.
> Don’t forget to delete the cookies of that web portal to start with a clean session when training the web portal procedure for downloading your bills.
>
> When `BillCollector.py` is run in debug mode, by default, it pauses at each step of the recipe, downloads the HTML into `page_source.html` and waits for a SPACE keystroke to proceed.
> This lets you analyze the HTML for the web elements to be clicked or sent text (e.g., username) to.

   *Full example of a YAML recipe, which also includes an One-Time-Password step (OTP):*

   ```yaml
   ---
   services:
   - serviceName: "datev"
      actions:
         - step: 1
         description: "Click the login button to start the authentication process."
         actionType: "Click"
         parameters:
            locators:
               - locatorType: "CSS_SELECTOR"
               element: "[data-test-id=\"login-button\"]"
         - step: 2
         description: "Click the TOTP login button to proceed with two-factor authentication."
         actionType: "Click"
         parameters:
            locators:
               - locatorType: "CSS_SELECTOR"
               element: "[data-test-id=\"totp-login-button\"]"
         - step: 3
         description: "Focus on the username field for entering credentials."
         actionType: "Click"
         parameters:
            locators:
               - locatorType: "ID"
               element: "username"
         - step: 4
         description: "Enter the username into the username input field."
         actionType: "SendKeys"
         parameters:
            locators:
               - locatorType: "ID"
               element: "username"
            variable: "{USERNAME}"
         - step: 5
         description: "Enter the password into the password input field."
         actionType: "SendKeys"
         parameters:
            locators:
               - locatorType: "ID"
               element: "password"
            variable: "{PASSWORD}"
         - step: 6
         description: "Click the login button to submit the entered credentials."
         actionType: "Click"
         parameters:
            locators:
               - locatorType: "ID"
               element: "login"
         - step: 7
         description: "Enter the one-time password (OTP) into the verification field."
         actionType: "SendKeys"
         parameters:
            locators:
               - locatorType: "ID"
               element: "enterverificationcode"
            variable: "{OTP}"
         - step: 8
         description: "Press the Enter key to confirm the verification code."
         actionType: "SendKeys"
         parameters:
            locators:
               - locatorType: "ID"
               element: "enterverificationcode"
            variable: "ENTER"
         - step: 9
         description: "Click the button to load the documents in the dashboard."
         actionType: "Click"
         parameters:
            locators:
               - locatorType: "CSS_SELECTOR"
               element: "[data-test-id=\"load-documents-button\"]"
         - step: 10
         description: "Select a specific checkbox to choose a document."
         actionType: "Click"
         parameters:
            locators:
               - locatorType: "ID"
               element: "mat-mdc-checkbox-2-input"
         - step: 11
         description: "Download the selected document."
         actionType: "Download"
         parameters:
            locators:
               - locatorType: "CSS_SELECTOR"
               element: "[data-test-id=\"download-button\"]"
   ```
