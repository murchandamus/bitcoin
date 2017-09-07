// Copyright (c) 2012-2016 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include "wallet/coinselection.h"
#include "util.h"
#include "utilmoneystr.h"

// Descending order comparator
struct {
    bool operator()(CInputCoin a, CInputCoin b) const
    {
        return a.txout.nValue > b.txout.nValue;
    }
} descending;

struct CompareValueOnly
{
    bool operator()(const CInputCoin& t1,
                    const CInputCoin& t2) const
    {
        return t1.txout.nValue < t2.txout.nValue;
    }
};

bool SelectCoinsBnB(std::vector<CInputCoin>& utxo_pool, const CAmount& target_value, const CAmount& cost_of_change, std::set<CInputCoin>& out_set,
    CAmount& value_ret, std::vector<CAmount>& fee_vec, std::vector<CAmount>& long_term_fee_vec, CAmount& fee_ret)
{
    out_set.clear();
    value_ret = 0;

    if (utxo_pool.size() <=0) {
        return false;
    }

    int depth = 0;
    int tries = 100000;
    std::vector<std::pair<bool, bool>> selection; // First bool: select the utxo at this index; Second bool: traversing second branch of this utxo
    selection.assign(utxo_pool.size(), std::pair<bool, bool>(false, false));
    bool done = false;
    bool backtrack = false;

    // Sort the utxo_pool
    std::sort(utxo_pool.begin(), utxo_pool.end(), descending);

    // Calculate remaining
    CAmount remaining = 0;
    for (CInputCoin utxo : utxo_pool) {
        remaining += utxo.txout.nValue;
    }

    // Best solution
    CAmount curr_waste = 0;
    std::vector<std::pair<bool, bool>> best_selection;
    CAmount best_waste = MAX_MONEY;

    // Depth first search to find
    while (!done)
    {
        if (tries <= 0) { // Too many tries, exit
            break;
        } else if (value_ret > target_value + cost_of_change) { // Selected value is out of range, go back and try other branch
            backtrack = true;
        } else if (curr_waste > best_waste) { // Don't select things which we know will be more wasteful
            backtrack = true;
        } else if (value_ret >= target_value) { // Selected value is within range
            curr_waste += value_ret - target_value;
            if (curr_waste <= best_waste) {
                best_selection.assign(selection.begin(), selection.end());
                best_waste = curr_waste;
            }
            curr_waste -= value_ret - target_value;
            backtrack = true;
        } else if (depth >= (int)utxo_pool.size()) { // Reached a leaf node, no solution here
            backtrack = true;
        } else if (value_ret + remaining < target_value) { // Cannot possibly reach target with amount remaining
            if (depth == 0) { // At the first utxo, no possible selections, so exit
                break;
            } else {
                backtrack = true;
            }
        } else { // Continue down this branch
            // Assert that this utxo is not negative. It should never be negative, effective value calculation should have removed it
            assert(utxo_pool.at(depth).txout.nValue >= 0);

            // Remove this utxo from the remaining utxo amount
            remaining -= utxo_pool.at(depth).txout.nValue;
            // Increase waste
            curr_waste += fee_vec[depth] - long_term_fee_vec[depth];
            // Inclusion branch first (Largest First Exploration)
            selection.at(depth).first = true;
            value_ret += utxo_pool.at(depth).txout.nValue;
            ++depth;
        }

        // Step back to the previous utxo and try the other branch
        if (backtrack) {
            backtrack = false; // Reset
            --depth;

            // Walk backwards to find the first utxo which has not has its second branch traversed
            while (selection.at(depth).second) {
                // Reset this utxo's selection
                if (selection.at(depth).first) {
                    value_ret -= utxo_pool.at(depth).txout.nValue;
                    curr_waste -= fee_vec[depth] - long_term_fee_vec[depth];
                }
                selection.at(depth).first = false;
                selection.at(depth).second = false;
                remaining += utxo_pool.at(depth).txout.nValue;

                // Step back one
                --depth;

                if (depth < 0) { // We have walked back to the first utxo and no branch is untraversed. No solution, exit.
                    done = true;
                    break;
                }
            }

            if (!done) {
                // Now traverse the second branch of the utxo we have arrived at.
                selection.at(depth).second = true;

                // These were always included first, try excluding now
                selection.at(depth).first = false;
                value_ret -= utxo_pool.at(depth).txout.nValue;
                curr_waste -= fee_vec[depth] - long_term_fee_vec[depth];
                ++depth;
            }
        }
        --tries;
    }

    // Check for solution
    if (best_selection.empty()) {
        return false;
    }

    // Set output set
    value_ret = 0;
    for (unsigned int i = 0; i < best_selection.size(); ++i) {
        if (best_selection.at(i).first) {
            out_set.insert(utxo_pool.at(i));
            fee_ret += fee_vec.at(i);
            value_ret += utxo_pool.at(i).txout.nValue;
        }
    }

    return true;
}

static void ApproximateBestSubset(const std::vector<CInputCoin>& vValue, const CAmount& nTotalLower, const CAmount& nTargetValue,
                                  std::vector<char>& vfBest, CAmount& nBest, int iterations = 1000)
{
    std::vector<char> vfIncluded;

    vfBest.assign(vValue.size(), true);
    nBest = nTotalLower;

    FastRandomContext insecure_rand;

    for (int nRep = 0; nRep < iterations && nBest != nTargetValue; nRep++)
    {
        vfIncluded.assign(vValue.size(), false);
        CAmount nTotal = 0;
        bool fReachedTarget = false;
        for (int nPass = 0; nPass < 2 && !fReachedTarget; nPass++)
        {
            for (unsigned int i = 0; i < vValue.size(); i++)
            {
                //The solver here uses a randomized algorithm,
                //the randomness serves no real security purpose but is just
                //needed to prevent degenerate behavior and it is important
                //that the rng is fast. We do not use a constant random sequence,
                //because there may be some privacy improvement by making
                //the selection random.
                if (nPass == 0 ? insecure_rand.randbool() : !vfIncluded[i])
                {
                    nTotal += vValue[i].txout.nValue;
                    vfIncluded[i] = true;
                    if (nTotal >= nTargetValue)
                    {
                        fReachedTarget = true;
                        if (nTotal < nBest)
                        {
                            nBest = nTotal;
                            vfBest = vfIncluded;
                        }
                        nTotal -= vValue[i].txout.nValue;
                        vfIncluded[i] = false;
                    }
                }
            }
        }
    }
}

bool RandomSelector(std::vector<CInputCoin>& utxo_pool, const CAmount& nTargetValue, std::set<CInputCoin>& out_set, CAmount& value_ret)
{
    out_set.clear();
    value_ret = 0;

    random_shuffle(utxo_pool.begin(), utxo_pool.end(), GetRandInt);

    for (const CInputCoin coin : utxo_pool)
    {
        if (coin.txout.nValue < nTargetValue + MIN_CHANGE) {
            out_set.insert(coin);
            value_ret += coin.txout.nValue;
        } else {
            return true;
        }
    }

    if (coin.txout.nValue < nTargetValue + MIN_CHANGE) {
        return false;
    }
}

bool LargestFirstSelector(std::vector<CInputCoin>& utxo_pool, const CAmount& nTargetValue, std::set<CInputCoin>& out_set, CAmount& value_ret)
{
    out_set.clear();
    value_ret = 0;

    std::sort(utxo_pool.begin(), utxo_pool.end(), CompareValueOnly());
    std::reverse(utxo_pool.begin(), utxo_pool.end());

    for (const CInputCoin coin : utxo_pool)
    {
        if (coin.txout.nValue < nTargetValue + MIN_CHANGE) {
            out_set.insert(coin);
            value_ret += coin.txout.nValue;
        } else {
            return true;
        }
    }

    if (coin.txout.nValue < nTargetValue ) {
        return false;
    }
}
