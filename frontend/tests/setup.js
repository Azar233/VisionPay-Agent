/**
 * Vitest 全局 setup
 * 在每个测试文件执行前自动运行
 */
import { vi } from "vitest";

// 模拟 Element Plus 的 ElMessage(避免测试中弹出消息框)
vi.mock("element-plus", async () => {
    const actual = await vi.importActual("element-plus");
    return {
        ...actual,
        ElMessage: {
            success: vi.fn(),
            error: vi.fn(),
            warning: vi.fn(),
            info: vi.fn(),
        },
    };
});