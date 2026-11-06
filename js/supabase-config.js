const supabaseUrl = 'https://rjlldqbqkmbgluoafapz.supabase.co';
const supabaseKey = 'sb_publishable_7sI-qeqiY0PWtgxVNKarsw_GXv_uT-4'; 

// We attach the client directly to the window object to prevent naming collisions
window.supabaseClient = window.supabase.createClient(supabaseUrl, supabaseKey);
