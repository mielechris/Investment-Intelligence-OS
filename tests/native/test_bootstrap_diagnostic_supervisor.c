/* Owned-child timeout/output/exit fixtures; no acquired runtime is invoked. */
#define main diagnostic_entrypoint
#include "../../scripts/iios_bootstrap_diagnostic.c"
#undef main
int main(int argc,char **argv){
 if(argc!=2)return 80;
 char out[4096],err[4096],log[4096];snprintf(log,sizeof log,"%s/controller.log",argv[1]);
 journal=open(log,O_WRONLY|O_CREAT|O_EXCL,0600);if(journal<0)return 81;deadline=now()+120;
 char *ok[]={"/usr/bin/true",NULL},*bad[]={"/usr/bin/false",NULL},*slow[]={"/bin/sleep","5",NULL},*large[]={"/usr/bin/yes",NULL};
 char **cases[]={ok,bad,slow,large};int expected[]={1,0,0,0};
 for(int i=0;i<4;i++){snprintf(out,sizeof out,"%s/case-%d.out",argv[1],i);snprintf(err,sizeof err,"%s/case-%d.err",argv[1],i);double start=now();int got=bounded(cases[i],out,err,i==2?0.1:5,1024);if(got!=expected[i]||now()-start>6)return 82;}
 int status;errno=0;if(waitpid(-1,&status,WNOHANG)!=-1||errno!=ECHILD)return 83;
 note("ALL_FOUR_FIXTURES_PASS_NO_UNREAPED_CHILDREN");close(journal);return 0;
}
