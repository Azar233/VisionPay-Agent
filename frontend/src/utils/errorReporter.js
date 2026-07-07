import { ElMessage } from "element-plus";

// 错误上报配置
// Day 4 先上报到控制台 + 本地存储，后续可以接入后端 API
const REPORT_TO_BACKEND = false; // 生产环境建议设为 true
const REPORT_API = "/api/errors/report";

/**
 * 统一上报错误信息
 * 当前实现: 输出到控制台 + 存入 localStorage
 */
function reportError(errorInfo) {
    // 1. 控制台输出 (开发调试用)
    console.error("[ErrorReporter]", errorInfo);

    // 2. 存入本地存储 (保留最近 50 条)
    try {
        const errors = JSON.parse(localStorage.getItem("error_logs") || "[]");
        errors.push({
            ...errorInfo,
            timestamp: new Date().toISOString(),
            url: window.location.href,
            userAgent: navigator.userAgent,
        });

        // 超出 50 条时，删除最旧的
        if (errors.length > 50) {
            errors.splice(0, errors.length - 50);
        }

        localStorage.setItem("error_logs", JSON.stringify(errors));
    } catch (e) {
        // localStorage 写入失败不影响程序主流程
        console.warn("ErrorReporter: localStorage写入失败", e);
    }

    // 3. 上报到后端 (生产环境启用)
    if (REPORT_TO_BACKEND) {
        fetch(REPORT_API, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(errorInfo),
        }).catch(() => {
            // 上报失败时静默处理，避免引发二次报错
        });
    }
}

/**
 * 初始化全局错误监控
 * @param {import('vue').App} app Vue 应用实例
 */
export function setupErrorReporting(app) {
    // 1. 捕获 Vue 组件渲染和生命周期错误
    app.config.errorHandler = (err, instance, info) => {
        reportError({
            type: "vue_error",
            message: err.message,
            stack: err.stack,
            component: info, // 错误发生所在组件的生命周期钩子
        });
        // 给用户友好的错误提示
        try {
            ElMessage?.error("页面渲染出错,请刷新重试");
        } catch {
            // Element Plus 未加载时静默处理
        }
    };

    // 2. 捕获 JavaScript 运行时错误
    window.onerror = (message, source, lineno, colno, error) => {
        reportError({
            type: "js_error",
            message: message,
            source: source,
            lineno: lineno,
            colno: colno,
            stack: error?.stack,
        });
    };

    // 3. 捕获未处理的 Promise 异常 (如未 catch 的 axios 请求报错)
    window.onunhandledrejection = (event) => {
        reportError({
            type: "promise_rejection",
            message: event.reason?.message || String(event.reason),
            stack: event.reason?.stack,
        });
        // 阻止默认的浏览器控制台红字输出 (因为我们已经自行处理了)
        event.preventDefault();
    };

    console.log("[ErrorReporter] 全局错误监控已启用");
}