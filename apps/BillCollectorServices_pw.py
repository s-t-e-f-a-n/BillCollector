import os
from BillCollectorHelpers import *

def retrieve_from_service_with_playwright(service, url, user, pwd, otp, debug):
    
    bcs = service_vars(usr=user, pwd=pwd, otp=otp, dbg=debug, dld=f"{os.path.dirname(os.path.realpath(__file__))}/{DOWNLOAD_DIR}", yml=None, drv=None)
    if not os.path.exists(bcs.dld):
        os.makedirs(bcs.dld)
#    bcs.drv = InitBrowser(bcs)
    bcs.drv.get(url)

