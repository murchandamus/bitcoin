// Copyright (c) 2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <node/mini_miner.h>

#include <consensus/amount.h>
#include <policy/feerate.h>
#include <primitives/transaction.h>
#include <timedata.h>
#include <util/check.h>
#include <util/moneystr.h>

#include <algorithm>
#include <numeric>
#include <utility>

namespace node {

MiniMiner::MiniMiner(const CTxMemPool& mempool, const std::vector<COutPoint>& outpoints)
{
    LOCK(mempool.cs);
    requested_outpoints = outpoints;
    // Find which outpoints to calculate bump fees for.
    // Anything that's spent by the mempool is to-be-replaced
    // Anything otherwise unavailable just has a bump fee of 0
    for (const auto& outpoint : outpoints) {
        if (const auto ptx{mempool.GetConflictTx(outpoint)}) {
            // This outpoint is already being spent by another transaction in the mempool.
            // We assume that the caller wants to replace this transaction (and its descendants).
            // This means we still need to calculate its ancestors bump fees, but after removing the
            // to-be-replaced entries. Note that this is only calculating bump fees and RBF fee
            // rules are not factored in here; those should be handled separately.
            to_be_replaced.insert(ptx->GetHash());
        }

        if (!mempool.exists(GenTxid::Txid(outpoint.hash))) {
            // This UTXO is either confirmed or not yet submitted to mempool.
            // In the former case, no bump fee is required.
            // In the latter case, we have no information, so just return 0.
            bump_fees.emplace(outpoint, 0);
        } else {
            // This UTXO is unconfirmed, in the mempool, and available to spend.
            auto it = requested_outpoints_by_txid.find(outpoint.hash);
            if (it != requested_outpoints_by_txid.end()) {
                it->second.push_back(outpoint);
            } else {
                std::vector<COutPoint> outpoints_of_tx({outpoint});
                requested_outpoints_by_txid.emplace(outpoint.hash, outpoints_of_tx);
            }
        }
    }

    // No unconfirmed UTXOs, so nothing mempool-related needs to be calculated.
    if (outpoints_needed_by_txid.empty()) return;

    // Calculate the cluster and construct the entry map.
    std::vector<uint256> txids_needed;
    for (const auto& [txid, outpoints]: requested_outpoints_by_txid) {
        txids_needed.push_back(txid);
    }
    const auto& cluster = mempool.CalculateCluster(txids_needed);
    // An empty cluster means that at least one of the transactions is missing from the mempool.
    // Since we only included things that exist in mempool, have not released the mutex, and would
    // have quit early if outpoints_needed_by_txid was empty, this should not be possible.
    Assume(!cluster.empty());
    for (const auto& txiter : cluster) {
        if (to_be_replaced.find(txiter->GetTx().GetHash()) == to_be_replaced.end()) {
            // Exclude entries that are going to be replaced.
            auto [mapiter, success] = entries_by_txid.emplace(txiter->GetTx().GetHash(), MiniMinerMempoolEntry(txiter));
            Assume(success);
            entries.push_back(mapiter);
        } else {
            auto outpoints_it = requested_outpoints_by_txid.find(txiter->GetTx().GetHash());
            if (outpoints_it != requested_outpoints_by_txid.end()) {
                // This UTXO is the output of a to-be-replaced transaction. Bump fee is 0; spending
                // this UTXO is impossible as it will no longer exist after the replacement.
                for (const auto& outpoint : outpoints_it->second) {
                    bump_fees.emplace(outpoint, 0);
                }
                requested_outpoints_by_txid.erase(outpoints_it);
            }
        }
    }

    // Remove the to-be-replaced transactions and build the descendant_set_by_txid cache.
    for (const auto& txiter : cluster) {
        const auto& txid = txiter->GetTx().GetHash();
        // Cache descendants for future use. Unlike the real mempool, a descendant MiniMinerMempoolEntry
        // will not exist without its ancestor MiniMinerMempoolEntry, so these sets won't be invalidated.
        std::vector<MockEntryMap::iterator> cached_descendants;
        cached_descendants.emplace_back(entries_by_txid.find(txid));
        // If a tx is to-be-replaced, remove any of its descendants so they can't fee-bump anything.
        // this case should be rare as the wallet won't normally attempt to replace transactions
        // with descendants.
        const bool remove = to_be_replaced.find(txid) != to_be_replaced.end();
        CTxMemPool::setEntries descendants;
        mempool.CalculateDescendants(txiter, descendants);

        for (const auto& desc_txiter : descendants) {
            auto desc_it{entries_by_txid.find(desc_txiter->GetTx().GetHash())};
            // It's possible the descendant has already been excluded, see cluster loop above.
            if (desc_it != entries_by_txid.end()) {
                if (remove) {
                    entries_by_txid.erase(desc_it);
                } else {
                    cached_descendants.push_back(desc_it);
                }
            }
        }
        if (!remove) descendant_set_by_txid.emplace(txid, std::move(cached_descendants));
    }
    // Release the mempool lock; we now have all the information we need for a subset of the entries
    // we care about. We will solely operate on the MiniMinerMempoolEntry map from now on.
    Assume(entries.size() == entries_by_txid.size());
    Assume(entries.size() == descendant_set_by_txid.size());
    Assume(in_block.empty());
    Assume(outpoints_needed_by_txid.size() <= outpoints.size());
}

// Compare by ancestor feerate, then iterator
struct AncestorFeerateComparator
{
    template<typename I>
    bool operator()(const I& a, const I& b) const {
        const CFeeRate a_feerate(a->second.GetModFeesWithAncestors(), a->second.GetSizeWithAncestors());
        const CFeeRate b_feerate(b->second.GetModFeesWithAncestors(), b->second.GetSizeWithAncestors());
        if (a_feerate != b_feerate) {
            return a_feerate > b_feerate;
        }
        return &(*a) > &(*b);
    }
};

void MiniMiner::DeleteAncestorPackage(const std::set<MockEntryMap::iterator, IteratorComparator>& ancestors)
{
    for (const auto& anc : ancestors) {
        auto vec_it = std::find(entries.begin(), entries.end(), anc);
        Assume(vec_it != entries.end());
        entries.erase(vec_it);
        entries_by_txid.erase(anc);
    }
}

void MiniMiner::BuildMockTemplate(const CFeeRate& target_feerate)
{
    while (!entries_by_txid.empty()) {
        // Sort again, since transaction removal may change some entries' ancestor feerates.
        std::sort(entries.begin(), entries.end(), AncestorFeerateComparator());

        // Pick highest ancestor feerate entry.
        auto best_iter = entries.begin();
        Assume(best_iter != entries.end());
        const auto ancestor_package_size = (*best_iter)->second.GetSizeWithAncestors();
        const auto ancestor_package_fee = (*best_iter)->second.GetModFeesWithAncestors();
        // Stop here. Everything that didn't "make it into the block" has bumpfee.
        if (ancestor_package_fee < target_feerate.GetFee(ancestor_package_size)) {
            break;
        }

        // Calculate ancestors on the fly. This lookup should be fairly cheap, and ancestor sets
        // change at every iteration, so this is more efficient than maintaining a cache.
        std::set<MockEntryMap::iterator, IteratorComparator> ancestors;
        std::set<MockEntryMap::iterator, IteratorComparator> to_process;
        ancestors.insert(*best_iter);
        to_process.insert(*best_iter);
        while (!to_process.empty()) {
            auto iter = to_process.begin();
            Assume(iter != to_process.end());
            const CTransaction& tx = (*iter)->second.GetTx();
            for (const auto& input : tx.vin) {
                if (auto parent_it{entries_by_txid.find(input.prevout.hash)}; parent_it != entries_by_txid.end()) {
                    to_process.insert(parent_it);
                    ancestors.insert(parent_it);
                }
            }
            to_process.erase(iter);
        }
        Assume(ancestor_package_size == std::accumulate(ancestors.cbegin(), ancestors.cend(), 0,
            [](int64_t sum, const auto it) {return sum + it->second.GetTxSize();}));
        Assume(ancestor_package_fee == std::accumulate(ancestors.cbegin(), ancestors.cend(), 0,
            [](CAmount sum, const auto it) {return sum + it->second.GetModifiedFee();}));

        // "Mine" all transactions in this ancestor set.
        for (const auto& anc : ancestors) {
            in_block.insert(anc->second.GetTx().GetHash());
            total_fees += anc->second.GetModifiedFee();
            total_vsize += anc->second.GetTxSize();
            auto it = descendant_set_by_txid.find(anc->second.GetTx().GetHash());
            Assume(it != descendant_set_by_txid.end());
            for (const auto& descendant : it->second) {
                descendant->second.vsize_with_ancestors -= anc->second.GetTxSize();
                descendant->second.fee_with_ancestors -= anc->second.GetModifiedFee();
            }
        }
        DeleteAncestorPackage(ancestors);
        Assume(entries.size() == entries_by_txid.size());
    }
}

std::map<COutPoint, CAmount> MiniMiner::CalculateBumpFees(const CFeeRate& target_feerate)
{
    // Build a block template until the target feerate is hit.
    BuildMockTemplate(target_feerate);
    Assume(in_block.empty() || CFeeRate(total_fees, total_vsize) >= target_feerate);

    // Each transaction that "made it into the block" has a bumpfee of 0, i.e. they are part of an
    // ancestor package with at least the target feerate and don't need to be bumped.
    for (const auto& txid : in_block) {
        // Not all of the block transactions were necessarily requested.
        auto it = requested_outpoints_by_txid.find(txid);
        if (it != requested_outpoints_by_txid.end()) {
            for (const auto& outpoint : it->second) {
                bump_fees.emplace(outpoint, 0);
            }
            requested_outpoints_by_txid.erase(it);
        }
    }
    // For each transaction that remains, the bumpfee is the cost to raise it and its ancestors
    // to the target feerate, target_feerate * ancestor_size - ancestor_fees
    for (const auto& [txid, outpoints] : requested_outpoints_by_txid) {
        auto it = entries_by_txid.find(txid);
        Assume(it != entries_by_txid.end());
        if (it != entries_by_txid.end()) {
            Assume(target_feerate.GetFee(it->second.GetSizeWithAncestors()) > it->second.GetModFeesWithAncestors());
            const CAmount bump_fee{target_feerate.GetFee(it->second.GetSizeWithAncestors())
                                   - it->second.GetModFeesWithAncestors()};
            Assume(bump_fee >= 0);
            for (const auto& outpoint : outpoints) {
                bump_fees.emplace(outpoint, bump_fee);
            }
        }
    }
    return bump_fees;
}

CAmount MiniMiner::CalculateTotalBumpFees(const CFeeRate& target_feerate)
{
    // Build a block template until the target feerate is hit.
    BuildMockTemplate(target_feerate);
    Assume(in_block.empty() || CFeeRate(total_fees, total_vsize) >= target_feerate);

    // All remaining ancestors that are not part of in_block must be bumped, but no other relatives (e.g. siblings, niblings, …)
    std::set<MockEntryMap::iterator, IteratorComparator> ancestors;
    std::set<MockEntryMap::iterator, IteratorComparator> to_process;

    for (const auto& outpoint : requested_outpoints) {
        const auto& txid = outpoint.hash;
        // Skip any ancestors that have a higher minerscore already
        if (in_block.find(txid) != in_block.end()) continue;
        auto iter = entries_by_txid.find(outpoint.hash);
        // This should never be possible. Catch in testing, but skip in production
        Assume(iter != entries_by_txid.end());
        if (iter == entries_by_txid.end()) continue;
        to_process.insert(iter);
        ancestors.insert(iter);
    }

    while (!to_process.empty()) {
        auto iter = to_process.begin();
        const CTransaction& tx = (*iter)->second.GetTx();
        for (const auto& input : tx.vin) {
            if (auto parent_it{entries_by_txid.find(input.prevout.hash)}; parent_it != entries_by_txid.end()) {
                to_process.insert(parent_it);
                ancestors.insert(parent_it);
            }
        }
        to_process.erase(iter);
    }

    CAmount total_fees = 0;
    CAmount total_vsize = 0;
    for (const auto& anc : ancestors) {
        total_fees += anc->second.GetModifiedFee();
        total_vsize += anc->second.GetTxSize();
    }

    CAmount target_fee = target_feerate.GetFee(total_vsize);
    return target_fee - total_fees;
}
} // namespace node
