# CSC - Catalog of Second Chances

_Catalog of Second Chances (CSC)_ tries to provide a platform and the
corresponding tools to leverage a database of uniquely identified, digitized
building components and materials to create designs that reuse these
components.

## Prerequisites

- This is research level code! As always: expect bugs, weird behaviour, things
not working, etc. pp.

## Software Structure

- The Catalog consists of a _database_, _backend_, _frontend_, and _Grasshopper interface_
- We use [_MongoDB Atlas_](https://www.mongodb.com/) as database
- The backend is implemented using [_FastAPI_](https://fastapi.tiangolo.com/)
- We use Python 3.9.18
- The frontend is implemented using the [_Next.JS_](https://nextjs.org/)
framework
- The frontend is designed to connect to the backend on the same server using JWT-based auth
- Grasshopper interface provides Python 3 components for direct integration with Rhino/Grasshopper
- Everything runs on a web server, in our case we use
[_Uberspace_](https://uberspace.de/)

## Current Versions

- **CSC FastAPI Backend**: 0.4.1.0
- **CSC React Frontend**: 0.4.3.3
- **CSC Grasshopper Interface**: 0.4.5.0

---

# Installation & Configuration

Start by cloning this repo onto your desktop computer.

## MongoDB and dbconfig.json

Either create a MongoDB atlas account and set up a new database or run a
MongoDB database by other means. Save your connection string / login
credentials once you have them.

## Creating a Secret Key for JWT Auth

Open a terminal and run the following command to create a random secret key
that will be used to sign JWT access tokens while authenticating with the
FastAPI backend:

```
$ openssl rand -hex 32

>> 09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7
```

- You will end up with a key like the above (__DON'T__ use the one in this
example!).
- If in doubt, have a look here for a detailed explanation of the auth setup:
[FastAPI OAuth2 with Password (and hashing), Bearer with JWT tokens]
(https://fastapi.tiangolo.com/tutorial/security/oauth2-jwt/#handle-jwt-tokens)

## Editing dbconfig.json

- Navigate to `... \csc\src\backend`
- Copy `dbconfig.template.json` and rename it to `dbconfig.json`
- Edit `dbconfig.json` and add your MongoDB credentials
- Paste your secret key from the previous step into the `'secret'` field of
your `dbconfig.json`

## Editing .env.local

- Navigate to `...\csc\src\frontend`
- Copy `.env.example` and rename it to `.env`
- Edit `.env` and paste your secret key into the `API_SECRET` field
- Also add your MongoDB credentials so that the frontend can directly authenticate with MongoDB
- Do the same with `.env.local.example`, following the comments given in the file

## Grasshopper Interface Setup

The CSC Grasshopper Interface consists of Python 3 components that can be used directly in Grasshopper:

- **Location**: `grasshopper_userobjects_src/` - Source files for development
- **Installation**: Copy `.ghuser` files from `grasshopper_userobjects/` to your Grasshopper UserObjects folder
- **Requirements**: Python 3 with packages: requests, numpy, scipy, scikit-learn
- **Authentication**: Use `CSC_SignIn` component first to authenticate with the backend

## Configuring Uberspace

If you want to setup _CSC_ on _Uberspace_, here are some guidelines. Please
also check the [Uberlab Guides](https://lab.uberspace.de/) for further / more
detailed information on the covered topics.

- Create a folder for running CSC and a virtual environment on your uberspace
server.

```
[user@servername ~]$ mkdir ~/csc
[user@servername ~]$ cd ~/csc
[user@servername csc]$ python3.9 -m venv venv
[user@servername csc]$ source venv/bin/activate
(venv) [user@servername ~]$
```

- Install necessary packages and then deactivate the venv

```
(venv) [user@servername csc]$ pip install gunicorn uvloop httptools
(venv) [user@servername csc]$ deactivate
[user@servername ~]$
```

## Uploading files

Use a file transfer software to upload the `backend` and `frontend` folders to
your web server. In our case the folder structure looks like this:

```
/home/user/
├─ csc/
│  ├─ venv/
│  ├─ backend/
│  ├─ frontend/
```

## Setting up FastAPI

We provide a pre-configured configuration file for gunicorn. Test if everything
is working by running:

```
[user@servername ~]$ ~/csc/venv/bin/gunicorn --config ~/csc/backend/conf.py --check-config
```

If there is no output, you should be good. For additional info on setting up
FastAPI on Uberspace, please check
[Uberlab](https://lab.uberspace.de/guide_fastapi/).

## Setting up the Next.js based React Frontend

The frontend runs using _Next.js_, which is a frontend framework based on
_React_. All that runs using _Node.js_. First off, we check our node version.
This repo assumes we run version 18:

```
[user@servername ~]$ uberspace tools version show node
Using 'Node.js' version: '18'
[user@servername ~]$
```

Once that is checked, navigate to `/home/user/csc/frontend` and run the
following commands:

```
npm install -g npm@latest

removed 2 packages, and changed 53 packages in 9s

24 packages are looking for funding
[user@servername frontend]$ npm i
up to date, audited 482 packages in 4s
[user@servername frontend]$
```

This should install all necessary packages using the node package manager
(npm). Once that is done, run:

```
[user@servername frontend]$ npm run build

> frontend@0.2.0.9 build
> next build

   ▲ Next.js 15.5.0
   - Environments: .env.local

   Creating an optimized production build ...
   ✓ Linting and checking validity of types
   ✓ Collecting page data
   ✓ Generating static pages (8/8)
   ✓ Collecting build traces
   ✓ Finalizing page optimization

Route (app)                              Size     First Load JS
┌ ○ /                                    141 B          84.5 kB
├ ○ /_not-found                          882 B          85.2 kB
├ λ /components                          244 kB          346 kB
├ λ /components/[component_id]           816 B          91.9 kB
├ ○ /findcomponent                       111 kB          203 kB
└ ○ /settings                            141 B          84.5 kB
+ First Load JS shared by all            84.4 kB
  ├ chunks/69-9d1319c8f23893a2.js        29 kB
  ├ chunks/fd9d1056-7473a1f6941f0e46.js  53.4 kB
  └ other shared chunks (total)          1.97 kB


○  (Static)   prerendered as static content
λ  (Dynamic)  server-rendered on demand using Node.js

[user@servername frontend]$ 
```

Now you should be almost set up! The last things to do are configuring services
and corresponding web backends...

### Upgrading Next.js

Use the official Next.js codemod to upgrade the frontend to a newer version:

```bash
# Upgrade to the latest patch (e.g. 16.0.7 -> 16.0.8)
npx @next/codemod upgrade patch

# Upgrade to the latest minor (e.g. 15.3.7 -> 15.4.8). This is the default.
npx @next/codemod upgrade minor

# Upgrade to the latest major (e.g. 15.5.7 -> 16.0.7)
npx @next/codemod upgrade major

# Upgrade to a specific version
npx @next/codemod upgrade 16

# Upgrade to the canary release
npx @next/codemod upgrade canary
```

### Services Config using Supervisor

Again, we will consider our setup case using Uberspace, which uses Supervisor
for services:

- On your computer, navigate to `...\csc\uberspaceconfig\etc\services.d`
- This folder contains two configuration files for _Supervisor_
- Transfer these files to Uberspace into `/home/yourusername/etc/services.d`
- Run the following commands:

```
[user@servername ~]$ supervisorctl reread
SERVICE: available
[user@servername ~]$ supervisorctl update
SERVICE: added process group
[user@servername ~]$ supervisorctl status
SERVICE                            RUNNING   pid 26020, uptime 0:03:14
```

### Configuring Web Backends

- _Gunicorn_ is set up to run the _FastAPI_ backend on Port 8000
- The _Next.js_ frontend is configured to run on Port 3000
- The Web Backends have to be set to the port that the apps are listening on!

- First, we list the active backends:

```
[user@servername ~]$ uberspace web backend list
/ apache (default)
[user@servername ~]$
```

- We will not use the default backend, so we delete it

```
[user@servername ~]$ uberspace web backend del /
The web backend has been deleted.
[user@servername ~]$
```

- Next we register a subdomain for our _FastAPI_ backend...

```
[user@servername ~]$ uberspace web domain add api.username.uber.space
The webserver's configuration has been adapted.
Now you can use the following records for your DNS:
    A -> 185.26.156.55
    AAAA -> 2a00:d0c0:200:0:b9:1a:9c:37
[user@servername ~]$
```

- Then we add the corresponding web backend for _FastAPI_

```
[user@servername ~]$ uberspace web backend set api.username.uber.space/ --http --port 8000
Set backend for api.username.uber.space/ to port 8000; please make sure something is listening!
You can always check the status of your backend using "uberspace web backend list".
[user@servername ~]$ 
```

- Lastly, we set our default backend to point to the _Next.js_...

```
[user@servername ~]$ uberspace web backend set / --http --port 3000
Set backend for / to port 3000; please make sure something is listening!
You can always check the status of your backend using "uberspace web backend list".
[user@servername ~]$ 
```

For further information please refer to the corresponding Uberspace manual and
Uberlab guides:
- [Uberspace Web Backends](https://manual.uberspace.de/web-backends/)
- [Uberspace Web Domains](https://manual.uberspace.de/web-domains/)


## Preview Generation CronJob

Preview generation is a separate python app that is run using a cronjob. To
test the preview generation, SSH into the server, activate the venv and run it
using the command line:

```
[user@servername csc]$ source venv/bin/activate
(venv) [user@servername ~]$
(venv) [user@servername ~]$ python /home/ddu/csc/backend/main_previewgen.py
```

To check if it is already a cronjob on your instance, run:
```
[user@servername csc]$ crontab -l
```

To add the cronjob to your crontab run:

```
[user@servername csc]$ crontab -e
```

...to open the crontab in an editor and then add:

```
*/30 * * * * /home/ddu/csc/venv/bin/python3.9 /home/ddu/csc/backend/main_previewgen.py >> /home/ddu/csc/backend/logs/previewgen_cronjob.log 2>&1
```

This will run the preview generation script every 30 minutes and write the
results to a logging file.

## Grasshopper XML Sync CronJob

The GH XML sync automatically mirrors pasteable XML files from the private GitHub
repository to make them available for copy-to-clipboard functionality on the
frontend.

### Configuration

Add the following to your `dbconfig.json`:

```json
{
  "gh_xml_cache_dir": "/home/ddu/csc/backend/static/ghxml",
  "github_repo_url": "https://github.com/your-org/your-repo",
  "github_repo_token": "your_github_token"
}
```

### Testing

To test the sync script manually, SSH into the server and run:

```bash
[user@servername csc]$ /bin/bash /home/ddu/csc/src/backend/ghxml_sync.sh
```

This will clone (if needed) and sync only the `grasshopper_userobjects_xml/`
folder from your private GitHub repository. Check the log file for results:

```bash
[user@servername csc]$ tail -f /home/ddu/csc/backend/logs/ghxml_sync.log
```

### Setting up the CronJob

To add the sync cronjob, copy the configuration from
`uberspaceconfig/crontab/ghxml_sync_cronjob.ini` or add it manually:

```bash
[user@servername csc]$ crontab -e
```

Add this line:

```
*/30 * * * * /bin/bash /home/ddu/csc/src/backend/ghxml_sync.sh >> /home/ddu/csc/backend/logs/ghxml_sync.log 2>&1
```

This will run the sync every 30 minutes and log results to the log file.

## OpenAPI Model Generation

This project uses OpenAPI schema generation to keep frontend TypeScript models in sync with backend Pydantic models.

### How It Works

1. **Backend**: Pydantic models are enhanced with OpenAPI documentation and Field descriptions
2. **Schema Endpoint**: `/schema/component` endpoint exposes the ComponentModel schema
3. **Frontend Generation**: Script fetches schema and generates TypeScript interfaces
4. **Auto-sync**: Models are automatically kept in sync

### Usage

#### Generate Models

```bash
# Generate ComponentModel from backend
npm run generate:models
```

#### Development Workflow

1. **Update Backend Model**: Modify Pydantic model in `src/backend/apps/Catalog/models.py`
2. **Restart Backend**: Restart FastAPI to regenerate OpenAPI schema
3. **Generate Frontend Models**: Run `npm run generate:models`
4. **Use Generated Models**: Import from `src/generated/ComponentModel`

#### Import Generated Models

```typescript
// Instead of importing from components/common/models
// import { ComponentData } from '@/components/common/models';

// Import from generated models
import { ComponentModel, ComponentType, ComponentComplexity } from '@/generated/ComponentModel';

// Use the generated interface
const component: ComponentModel = {
  _id: "uuid",
  type: "slab",
  material: "concrete",
  // ... other properties
};
```

### File Structure

```
src/frontend/
├── scripts/
│   └── generate-models.ts    # Generation script
├── generated/                 # Auto-generated models
│   ├── ComponentModel.ts     # Generated ComponentModel interface
│   └── index.ts             # Export index
└── package.json              # Contains generate:models script
```

## Testing

To run all available tests, call
```
invoke test
```

## Linting

To lint all python code, call
```
invoke lint
```

# Credits

## Public Funding

Part of this research was conducted within the Project _Fertigteil 2.0 -
Real-digital process chains for the production of built-in concrete
components_. The project _Fertigteil 2.0 (Precast Concrete Components 2.0)_
was funded by the Federal Ministry of Education and Research Germany (BMBF)
through the funding measure Resource-efficient circular economy - Building and
mineral cycles (ReMin).

## Student Work

- The `csc_labels` python code to create QR-Code labels was developed by Mirko
Dutschke. The code has been refactored as a python module and integrated by
Max Benjamin Eschenbach.
- The `csc_sheetscan` python module was developed based on the scanning setup
for sheets that was developed by Mirko Dutschke. The functional code has been
written by Max Benjamin Eschenbach.
- **NEW**: The CSC Grasshopper Interface components were developed and standardized by Max Benjamin Eschenbach, providing Python 3 components for direct integration with Rhino/Grasshopper workflows.

## Licensing

- Original code is licensed under the MIT License.
- The `csc_sheetscan` module makes heavy use of the
[OpenCV](https://opencv.org/) library, more specifically its
[pre-built packages for python](https://anaconda.org/conda-forge/opencv)
via conda-forge.

## References

- The technical main inspiration for the _Catalog of Second Chances_
interface is the [Catalog Explorer](https://github.com/ibois-epfl/Catalog-explorer)
by [@AymbericBr](https://github.com/AymericBr).
- Another huge inspiration and reference is the
[Timberstone Project](https://epfl-enac.github.io/MANSLAB-IBOIS-EESD-timberstone/),
which is the origin of abovementioned Catalog Explorer.

# To-Do & Extension Ideas

## Possible Future Integrations

- **Grasshopper Interface Enhancements**: Additional geometry processing components, parametric design tools
- **Mobile Applications**: Native mobile apps for field work and component identification
- **AI Integration**: Machine learning for automatic component classification and quality assessment
- **BIM Integration**: Direct integration with Revit, ArchiCAD, and other BIM software
