// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2020 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <policy/feerate.h>

#include <tinyformat.h>

CFeeRate::CFeeRate(CAmount nFeePaid, uint32_t num_bytes)
{
    const int64_t nSize{num_bytes};

    if (nSize > 0) {
        m_sats_per_kvB = nFeePaid * 1000 / nSize;
    } else {
        m_sats_per_kvB = 0;
    }
}

CAmount CFeeRate::GetFee(uint32_t num_bytes) const
{
    const int64_t nSize{num_bytes};

    CAmount nFee = m_sats_per_kvB * nSize / 1000;

    if (nFee == 0 && nSize != 0) {
        if (m_sats_per_kvB > 0) nFee = CAmount(1);
        if (m_sats_per_kvB < 0) nFee = CAmount(-1);
    }

    return nFee;
}

std::string CFeeRate::ToString(FeeEstimateMode fee_estimate_mode) const
{
    switch (fee_estimate_mode) {
    case FeeEstimateMode::SAT_VB: return strprintf("%d.%03d %s/vB", m_sats_per_kvB / 1000, m_sats_per_kvB % 1000, CURRENCY_ATOM);
    default:                      return strprintf("%d.%08d %s/kvB", m_sats_per_kvB / COIN, m_sats_per_kvB % COIN, CURRENCY_UNIT);
    }
}
