// Protects pages by kicking unauthenticated users back to index.html
async function checkAuth() {
    const { data: { session } } = await window.supabaseClient.auth.getSession();
    if (!session) {
        window.location.href = 'index.html';
    }
}
checkAuth();

async function logout() {
    await window.supabaseClient.auth.signout();
    window.location.href = 'index.html';
}
