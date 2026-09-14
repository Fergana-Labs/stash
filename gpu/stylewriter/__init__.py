"""Stylewriter's GPU side: train a voice adapter, draft with it, judge drafts.

Deployed on its own to Modal (`cd gpu && modal deploy -m stylewriter.modal_app`)
and reached by the backend over one proxy-authenticated web endpoint. Only
`modal_app.py` imports Modal or any ML library; everything else here is plain
Python that can be tested on a laptop.
"""
