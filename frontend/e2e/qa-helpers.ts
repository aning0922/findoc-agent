import type { Page } from '@playwright/test';
export async function manageQASources(page: Page) { await page.getByRole('button', { name: '管理来源', exact: true }).click(); }
export async function finishQASources(page: Page) { await page.getByRole('button', { name: '完成资料选择', exact: true }).click(); }
export async function openQAHistory(page: Page) { await page.getByRole('button', { name: '历史问答', exact: true }).click(); }
