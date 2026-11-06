// Protects pages by kicking unauthenticated users back to index.html
async function checkAuth() {
    const { data: { session } } = await supabase.auth.getSession();
    if (!session) {
        window.location.href = 'index.html';
    }
}
checkAuth();

async function logout() {
    await supabase.auth.signOut();
    window.location.href = 'index.html';
}
