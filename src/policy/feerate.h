// Copyright (c) 2009-2010 Satoshi Nakamoto
// Copyright (c) 2009-2020 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#ifndef BITCOIN_POLICY_FEERATE_H
#define BITCOIN_POLICY_FEERATE_H

#include <amount.h>
#include <serialize.h>

#include <string>

const std::string CURRENCY_UNIT = "BTC"; // One formatted unit
const std::string CURRENCY_ATOM = "sat"; // One indivisible minimum value unit

/* Used to determine type of fee estimation requested */
enum class FeeEstimateMode {
    UNSET,        //!< Use default settings based on other criteria
    ECONOMICAL,   //!< Force estimateSmartFee to use non-conservative estimates
    CONSERVATIVE, //!< Force estimateSmartFee to use conservative estimates
    BTC_KVB,      //!< Use BTC/kvB fee rate unit
    SAT_VB,       //!< Use sat/vB fee rate unit
};

/** Fee rate in satoshis per kilovbyte: CAmount / kvB */
class CFeeRate
{
private:
    /** fee rate in [sat/kvB] (satoshis per kilovirtualbyte) */
    CAmount nSatoshisPerK;

public:
    /** Fee rate of 0 satoshis per kB */
    CFeeRate() : nSatoshisPerK(0) { }
    template<typename I>
    explicit CFeeRate(const I _nSatoshisPerK): nSatoshisPerK(_nSatoshisPerK) {
        // We've previously had bugs creep in from silent double->int conversion...
        static_assert(std::is_integral<I>::value, "CFeeRate should be used without floats");
    }

    /**
     * Constructor for a fee rate in [sat/kvB]
     *
     * Calculates the fee rate of a transaction from its absolute fee and
     * vsize.
     *
     * Deprecated use to be replaced by dedicated functions: can be used to
     * convert a fee rate with a different unit to CFeeRate by passing the fee
     * rate in `nFeePaid` and the ratio as a divisor in `num_bytes`. E.g.
     * convert [BTC/kvB] to CFeeRate by multiplying input fee rate by COIN and
     * passing 1000 to num_bytes:
     * nFeePaid [BTC/kvB] × 1e8 [sat/BTC] / 1e3 [vB/kvB] = CFeeRate [sat/kvB]
     *
     * param@[in]   nFeePaid    The fee paid by a transaction in satoshis |
     *                          alt use: fee rate in e.g. [BTC/kvB] or [sat/B]
     * param@[in]   num_bytes   The vsize of a transaction in vbytes |
     *                          alt use: divisor for converting a fee rate
     *                          denominated in another unit to [sat/kvB]
     */
    CFeeRate(const CAmount& nFeePaid, uint32_t num_bytes);
    /**
     * Return the fee to achieve a fee rate of nSatoshisPerK for a given
     * vsize in vbytes.
     * param@[in]   num_bytes   The vsize to calculate an absolute fee for
     */
    CAmount GetFee(uint32_t num_bytes) const;
    /** Returns the fee rate in [sat/kvB] */
    CAmount GetFeePerK() const { return GetFee(1000); }
    friend bool operator<(const CFeeRate& a, const CFeeRate& b) { return a.nSatoshisPerK < b.nSatoshisPerK; }
    friend bool operator>(const CFeeRate& a, const CFeeRate& b) { return a.nSatoshisPerK > b.nSatoshisPerK; }
    friend bool operator==(const CFeeRate& a, const CFeeRate& b) { return a.nSatoshisPerK == b.nSatoshisPerK; }
    friend bool operator<=(const CFeeRate& a, const CFeeRate& b) { return a.nSatoshisPerK <= b.nSatoshisPerK; }
    friend bool operator>=(const CFeeRate& a, const CFeeRate& b) { return a.nSatoshisPerK >= b.nSatoshisPerK; }
    friend bool operator!=(const CFeeRate& a, const CFeeRate& b) { return a.nSatoshisPerK != b.nSatoshisPerK; }
    CFeeRate& operator+=(const CFeeRate& a) { nSatoshisPerK += a.nSatoshisPerK; return *this; }
    std::string ToString(const FeeEstimateMode& fee_estimate_mode = FeeEstimateMode::BTC_KVB) const;

    SERIALIZE_METHODS(CFeeRate, obj) { READWRITE(obj.nSatoshisPerK); }
};

#endif //  BITCOIN_POLICY_FEERATE_H
