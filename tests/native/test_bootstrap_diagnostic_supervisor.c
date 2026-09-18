/* Owned-child timeout/output/exit fixtures; no acquired runtime is invoked. */
#define proc_pidinfo fixture_pidinfo
#define main diagnostic_entrypoint
#include "../../scripts/iios_bootstrap_diagnostic.c"
#undef main
#undef proc_pidinfo
static int identity_case;
int fixture_pidinfo(int pid,int flavor,uint64_t arg,void *buffer,int size){
 (void)arg;if(flavor!=PROC_PIDT_SHORTBSDINFO||size!=sizeof(struct proc_bsdshortinfo))return 0;
 struct proc_bsdshortinfo *info=buffer;memset(info,0,sizeof *info);info->pbsi_pid=(uint32_t)pid;info->pbsi_ppid=677;
 if(identity_case==1)return size-1;
 if(identity_case==2)info->pbsi_pid++;
 if(identity_case==3)info->pbsi_ppid=(uint32_t)pid;
 if(identity_case==4)info->pbsi_ppid=1;
 return size;
}
static int identity_fixtures(void){
 for(identity_case=0;identity_case<5;identity_case++){pid_t child=fork();if(child<0)return 0;if(!child){alarm(3);pid_t parent=ancestor_parent(879);_exit(parent==677?0:2);}
 int status;if(waitpid(child,&status,0)!=child||!WIFEXITED(status)||WEXITSTATUS(status)!=(identity_case?1:0))return 0;}return 1;
}
int main(int argc,char **argv){
 if(argc!=2)return 80;
 if(!identity_fixtures())return 84;
 char out[4096],err[4096],log[4096];snprintf(log,sizeof log,"%s/controller.log",argv[1]);
 journal=open(log,O_WRONLY|O_CREAT|O_EXCL,0600);if(journal<0)return 81;deadline=now()+120;
 char *ok[]={"/usr/bin/true",NULL},*bad[]={"/usr/bin/false",NULL},*slow[]={"/bin/sleep","5",NULL},*large[]={"/usr/bin/yes",NULL};
 char **cases[]={ok,bad,slow,large};int expected[]={1,0,0,0};
 for(int i=0;i<4;i++){snprintf(out,sizeof out,"%s/case-%d.out",argv[1],i);snprintf(err,sizeof err,"%s/case-%d.err",argv[1],i);double start=now();int got=bounded(cases[i],out,err,i==2?0.1:5,1024);if(got!=expected[i]||now()-start>6)return 82;}
 int status;errno=0;if(waitpid(-1,&status,WNOHANG)!=-1||errno!=ECHILD)return 83;
 note("ALL_FOUR_FIXTURES_PASS_NO_UNREAPED_CHILDREN");close(journal);return 0;
}
