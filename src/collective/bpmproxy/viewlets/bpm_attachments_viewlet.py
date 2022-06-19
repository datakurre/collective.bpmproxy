# -*- coding: utf-8 -*-

from plone.app.layout.viewlets import ViewletBase


class BpmAttachmentsViewlet(ViewletBase):
    def update(self):
        pass

    def index(self):
        if self.view.attachments_enabled:
            return super(BpmAttachmentsViewlet, self).render()
        else:
            return u""
