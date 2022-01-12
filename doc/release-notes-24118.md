Add `sweepwallet` RPC
-----

The `sweepwallet` RPC spends some given UTXOs' complete balance to one or more
receivers without creating change.

By default, the `sweepwallet` RPC will empty the wallet completely leaving no
UTXOs behind. Optionally, the `sendmax` option allows skipping uneconomic UTXOs
and therefore maximizing the received amount.

The `sweepwallet` RPC can process a combination of receiver addresses with and
without amounts specified. The specified amounts are paid first, and the
remainder split among the receivers with unspecified amounts. At least one
address must be provided without unspecified amount to receive the balance left
after fees.

Instead of the complete UTXO pool, the call can be used to create a transaction
from a specific UTXO set. We recommend using `sweepwallet` to empty wallets
or to spend specific UTXOs in full.

The `sweepwallet` RPC therefore provides a less cumbersome way of spending
specific UTXOs or emptying wallets than subtract fee from output/amount (SFFO).
If the user wishes to specify a budget rather than a set of UTXOs to delimit a
transaction, they should continue to use SFFO.
