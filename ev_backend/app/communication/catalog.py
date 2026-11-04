"""Public taxonomy and split-specific scenario definitions; not agent inputs."""
VERSION = 'communication-v1'
ROOTS = {
    'none': (None, None),
    'charger_controller_timeout': ('session_fails_to_start', 'charger'),
    'vehicle_bms_fault': ('vehicle_specific_or_telematics_issue', 'bms'),
    'authorization_conflict': ('session_fails_to_start', 'app'),
    'payment_conflict': ('payment_or_billing_failure', 'payment'),
    'connector_fault': ('connector_or_charger_hardware_fault', 'connector'),
    'network_delay': ('network_or_connectivity_issue', 'network'),
    'network_loss': ('network_or_connectivity_issue', 'network'),
    'network_duplicate': ('network_or_connectivity_issue', 'network'),
    'stale_availability': ('charger_availability_mismatch', 'csms'),
    'metering_mismatch': ('payment_or_billing_failure', 'csms'),
    'inconclusive': (None, None),
}
SPLITS = ('train', 'validation', 'test')

# Each split uses a different fault trigger/operation and disjoint numeric
# configuration bands. The normal lifecycle is shared infrastructure, not a
# shared labelled scenario. Generalization is across these authored variants.
OPERATIONS = {
    'train': {'network_delay': 'Authorize', 'network_loss': 'RequestStartTransaction',
              'network_duplicate': 'TransactionEvent.Started', 'charger_controller_timeout': 'RequestStartTransaction'},
    'validation': {'network_delay': 'ChargeParameterDiscoveryReq', 'network_loss': 'Authorize',
                   'network_duplicate': 'MeterValues', 'charger_controller_timeout': 'ConnectorLock'},
    'test': {'network_delay': 'TransactionEvent.Ended', 'network_loss': 'ChargeParameterDiscoveryReq',
             'network_duplicate': 'PaymentCapture', 'charger_controller_timeout': 'SetChargingProfile'},
}


def templates():
    return [{'template_id': f'{VERSION}-{split}-{i:02d}', 'split': split, 'scenario': root,
             'operation': OPERATIONS[split].get(root), 'variant': SPLITS.index(split)}
            for split in SPLITS for i, root in enumerate(ROOTS)]


def root_category(root):
    return ROOTS.get(root, (None, None))[0]
