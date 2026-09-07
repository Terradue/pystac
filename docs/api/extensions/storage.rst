pystac.extensions.storage
============================

.. automodule:: pystac.extensions.storage
   :members:
   :undoc-members:

Lifecycle rules
--------------

Lifecycle support follows the storage proposal at commit
``7927d9b835eb438e0ae9a27c23880d675eba3977``. Rules are keyed by identifier;
rule objects contain only a trigger and an action. Manual triggers are no
longer supported.

.. code-block:: python

   from pystac.extensions.storage import (
       StorageLifecycle,
       StorageLifecycleAgeTrigger,
       StorageLifecycleRule,
       StorageLifecycleTransitionAction,
   )

   lifecycle = StorageLifecycle.create(
       managed_by="application",
       rules={
           "archive": StorageLifecycleRule.create(
               trigger=StorageLifecycleAgeTrigger.create(
                   from_="/properties/created", after="P30D"
               ),
               action=StorageLifecycleTransitionAction.create(target="cold"),
           )
       },
   )

The other variants are ``StorageLifecycleDatetimeTrigger.create(at=...)`` and
``StorageLifecycleExpireAction.create()``. Timestamp fields contain JSON Pointers;
transition targets name another scheme in the same ``storage:schemes`` map.

``StorageLifecycleTrigger.from_dict`` and ``StorageLifecycleAction.from_dict``
select a concrete class using ``type``. Rule accessors do the same and return
unions of the concrete variants, whose ``type`` properties have literal types.
Each variant exposes only its own fields. The discriminator is read-only; replace
a rule's trigger or action to switch variants. Unsupported types and missing
required variant fields raise errors.

Models retain their backing dictionaries, so edits to nested model fields update
the containing STAC object. Complete format and schema validation is separate
from model construction. This proposal does not change the released schema URI.
