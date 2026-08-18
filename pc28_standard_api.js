/**
 * PC28 Standard API - 统一数据接口模块
 * 支持多源自动降级：pc28.help → pgsoft → 28api → byw.bet
 * 全局实例: window.pc28
 */
(function (global) {
    'use strict';

    const SOURCES = [
        { name: 'pc28.help',  type: 'pc28help' },
        { name: 'pgsoft',     type: 'pgsoft' },
        { name: '28api',      type: 'api28' },
        { name: 'byw',        type: 'byw' }
    ];

    const TIMEOUT = 8000;

    // ========== 工具函数 ==========
    function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

    function normalize(raw, sourceType) {
        // 统一字段映射
        const map = {
            period:  raw.issue || raw.period || raw.id || raw.nbr || '',
            b1:      parseInt(raw.num1 || raw.b1 || raw.n1 || 0),
            b2:      parseInt(raw.num2 || raw.b2 || raw.n2 || 0),
            b3:      parseInt(raw.num3 || raw.b3 || raw.n3 || 0),
            sum:     parseInt(raw.sum || raw.total || 0),
            countdown: raw.countdown || raw.cd || null,
            time:    raw.time || raw.opentime || raw.drawTime || ''
        };
        if (!map.sum && (map.b1 + map.b2 + map.b3)) {
            map.sum = map.b1 + map.b2 + map.b3;
        }
        map.size  = map.sum >= 14 ? '大' : '小';
        map.parity = map.sum % 2 === 1 ? '单' : '双';
        map.combo = map.size + map.parity;
        return map;
    }

    // ========== 各源抓取器 ==========
    async function fetchPc28Help(endpoint) {
        const url = `https://pc28.help/api/${endpoint}`;
        const ctrl = new AbortController();
        const tid = setTimeout(() => ctrl.abort(), TIMEOUT);
        try {
            const r = await fetch(url, { signal: ctrl.signal });
            clearTimeout(tid);
            if (!r.ok) throw new Error(`pc28.help ${endpoint} HTTP ${r.status}`);
            const j = await r.json();
            return j;
        } finally { clearTimeout(tid); }
    }

    async function fetchPgSoft(endpoint, params) {
        const base = 'http://api.pgsoft.one/api/28';
        const qs = new URLSearchParams({ type: 'canada28', ...params }).toString();
        const url = `${base}/${endpoint}?${qs}`;
        const ctrl = new AbortController();
        const tid = setTimeout(() => ctrl.abort(), TIMEOUT);
        try {
            const r = await fetch(url, { signal: ctrl.signal });
            clearTimeout(tid);
            if (!r.ok) throw new Error(`pgsoft ${endpoint} HTTP ${r.status}`);
            return await r.json();
        } finally { clearTimeout(tid); }
    }

    // ========== 核心：带降级的抓取 ==========
    async function tryFetch(fetchFn, validator) {
        try {
            const data = await fetchFn();
            if (validator(data)) return data;
        } catch (e) { /* 继续下一个源 */ }
        return null;
    }

    // ========== 公开 API ==========
    const api = {
        /**
         * 获取最新一期开奖
         * @returns {Promise<Object>} { period, b1, b2, b3, sum, size, parity, combo, countdown, time, source }
         */
        async getLatest() {
            // 尝试 pc28.help
            let data = await tryFetch(
                () => fetchPc28Help('kj.json'),
                j => j && (j.issue || j.period || j.nbr)
            );
            if (data) {
                const n = normalize(data, 'pc28help');
                n.source = 'pc28.help';
                return n;
            }

            // 降级 pgsoft
            data = await tryFetch(
                () => fetchPgSoft('latest', { limit: 1 }),
                j => j && (j.data || j.list || j.rows)
            );
            if (data) {
                const arr = data.data || data.list || data.rows || data;
                const item = Array.isArray(arr) ? arr[0] : arr;
                const n = normalize(item, 'pgsoft');
                n.source = 'pgsoft';
                return n;
            }

            throw new Error('所有数据源均不可用');
        },

        /**
         * 获取历史开奖
         * @param {number} limit 期数
         * @returns {Promise<Array>}
         */
        async getHistory(limit = 50) {
            // pc28.help
            try {
                const data = await fetchPc28Help(`kj.json?limit=${limit}`);
                if (data && (data.list || data.data || Array.isArray(data))) {
                    const arr = data.list || data.data || data;
                    return arr.slice(0, limit).map(r => normalize(r, 'pc28help'));
                }
            } catch(e) {}

            // pgsoft
            try {
                const data = await fetchPgSoft('history', { page: 1, limit });
                if (data) {
                    const arr = data.data || data.list || data.rows || [];
                    return arr.slice(0, limit).map(r => normalize(r, 'pgsoft'));
                }
            } catch(e) {}

            return [];
        },

        /**
         * 获取双组预测
         * @returns {Promise<Object>}
         */
        async getDoubleGroup() {
            try { return await fetchPc28Help('sz.json'); } catch(e) {}
            return { data: [] };
        },

        /**
         * 获取杀组预测
         * @returns {Promise<Object>}
         */
        async getKillGroup() {
            try { return await fetchPc28Help('sha.json'); } catch(e) {}
            return { data: [] };
        },

        /**
         * 获取单双预测
         */
        async getDS() {
            try { return await fetchPc28Help('ds.json'); } catch(e) {}
            return { data: [] };
        },

        /**
         * 获取大小预测
         */
        async getDX() {
            try { return await fetchPc28Help('dx.json'); } catch(e) {}
            return { data: [] };
        },

        /**
         * 获取遗漏统计
         */
        async getMissStats() {
            try { return await fetchPc28Help('yl.json'); } catch(e) {}
            return { data: [] };
        },

        /**
         * 获取今日已开次数
         */
        async getTodayCount() {
            try { return await fetchPc28Help('yk.json'); } catch(e) {}
            return { data: [] };
        },

        /**
         * 获取长龙数据
         */
        async getDragons() {
            const result = {};
            for (const k of ['xh', 'jt', 'abb', 'pl']) {
                try {
                    const r = await fetchPc28Help(`${k}.json`);
                    result[k] = r;
                } catch(e) { result[k] = null; }
            }
            return result;
        },

        /**
         * 聚合预览（一次拿全）
         */
        async getPreview() {
            try { return await fetchPc28Help('preview.json'); } catch(e) {}
            return null;
        },

        /**
         * 一次性拉取所有核心数据
         */
        async fetchAll() {
            const [latest, sz, sha, ds, dx, yl, dragons] = await Promise.allSettled([
                this.getLatest(),
                this.getDoubleGroup(),
                this.getKillGroup(),
                this.getDS(),
                this.getDX(),
                this.getMissStats(),
                this.getDragons()
            ]);
            return {
                latest:  latest.status === 'fulfilled' ? latest.value : null,
                doubleGroup: sz.status === 'fulfilled' ? sz.value : { data: [] },
                killGroup:  sha.status === 'fulfilled' ? sha.value : { data: [] },
                ds: ds.status === 'fulfilled' ? ds.value : { data: [] },
                dx: dx.status === 'fulfilled' ? dx.value : { data: [] },
                miss: yl.status === 'fulfilled' ? yl.value : { data: [] },
                dragons: dragons.status === 'fulfilled' ? dragons.value : {}
            };
        },

        /**
         * 轮询新期（自动回调）
         * @param {Function} onNewPeriod 新期回调
         * @param {number} intervalMs 轮询间隔
         */
        async startPolling(onNewPeriod, intervalMs = 30000) {
            let lastNbr = null;
            const tick = async () => {
                try {
                    const data = await this.getLatest();
                    if (data.period && data.period !== lastNbr) {
                        lastNbr = data.period;
                        if (onNewPeriod) onNewPeriod(data);
                    }
                } catch(e) { console.warn('[pc28] poll error:', e.message); }
            };
            await tick();
            setInterval(tick, intervalMs);
        }
    };

    // 暴露全局
    global.pc28 = api;

    // Node.js 兼容
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }

})(typeof window !== 'undefined' ? window : globalThis);

/**
 * 便捷函数（全局可用）
 */
async function getLatestPC28() {
    return window.pc28.getLatest();
}
async function fetchAllPC28() {
    return window.pc28.fetchAll();
}
function startPC28Polling(cb, ms) {
    return window.pc28.startPolling(cb, ms);
}
